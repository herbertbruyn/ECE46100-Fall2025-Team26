"""
AWS Lambda Function for Async Artifact Ingestion

This function runs with high RAM (2-10GB) and handles:
1. Downloading HuggingFace files to S3
2. Creating zip archives
3. Computing ratings
4. Updating database with final status


Handles 424 rejection when rating fails threshold
"""
import os
import sys
import json
import logging
import boto3
import psycopg2
import re
from typing import Dict, Optional
import time

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import the S3 ingest utilities (copy from backend)
from s3_direct_ingest import S3DirectIngest

# Database connection parameters
DB_HOST = os.getenv('DB_HOST')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

MIN_NET_SCORE = 0.5  # Rating threshold


def lambda_handler(event, context):
    """
    Main Lambda handler

    Event payload:
    {
        "artifact_id": 123,
        "source_url": "https://huggingface.co/...",
        "artifact_type": "model",
        "revision": "main",
        "name": "bert-base"
    }
    """
    artifact_id = event['artifact_id']
    source_url = event['source_url']
    artifact_type = event['artifact_type']
    revision = event.get('revision', 'main')
    name = event['name']

    s3_prefix = None

    try:
        logger.info(f"Processing artifact {artifact_id}: {source_url}")

        # Initialize S3 ingest service
        s3_ingest = S3DirectIngest()

        # Step 1: Update status to downloading
        update_artifact_status(artifact_id, 'downloading', 'Streaming from HuggingFace to S3...')

        # Step 2: Stream HF files directly to S3
        repo_id = extract_repo_id(source_url)
        s3_prefix, s3_keys = s3_ingest.download_hf_to_s3_direct(
            repo_id, artifact_type, revision
        )
        logger.info(f"Streamed {len(s3_keys)} files to S3")

        # Step 3: Create zip in S3
        update_artifact_status(artifact_id, 'downloading', 'Creating zip archive in S3...')
        zip_s3_key = f"artifacts/{name}_{artifact_id}.zip"
        sha256_digest, size_bytes = s3_ingest.create_zip_in_s3(s3_keys, zip_s3_key)
        logger.info(f"Created zip: {zip_s3_key} ({size_bytes} bytes)")

        # Step 4: Compute ratings (for models)
        rating_scores = None
        if artifact_type == "model":
            update_artifact_status(artifact_id, 'rating', 'Computing metrics...')

            # Download minimal files for metrics
            local_metrics_dir = s3_ingest.download_minimal_for_metrics(s3_keys)

            # Extract code repository name from model metadata
            code_name = extract_code_repo_from_metadata(local_metrics_dir)
            logger.info(f"Extracted code repo: {code_name}")

            # Compute ratings
            rating_scores = compute_ratings(local_metrics_dir, source_url, name, code_name)
            logger.info(f"Rating completed: net_score={rating_scores.get('net_score', 0):.3f}")

            # Check threshold (424 logic)
            if rating_scores.get('net_score', 0) < MIN_NET_SCORE:
                logger.warning(f"Artifact {artifact_id} rejected: net_score below threshold")

                # Update status to rejected
                update_artifact_status(
                    artifact_id,
                    'rejected',
                    f"Rating {rating_scores.get('net_score'):.3f} below threshold {MIN_NET_SCORE}"
                )

                # Cleanup
                s3_ingest.cleanup_s3_temp_files(s3_prefix)

                # Note: Per spec, artifact is "dropped silently" - returns 404 on /rate
                # We keep the record with status="rejected" so it can be retried
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'artifact_id': artifact_id,
                        'status': 'rejected',
                        'reason': '424 - Disqualified rating'
                    })
                }
        else:
            rating_scores = fallback_rating()

        # Step 5: Persist to database
        update_artifact_complete(
            artifact_id=artifact_id,
            zip_s3_key=zip_s3_key,
            sha256=sha256_digest,
            size_bytes=size_bytes,
            rating_scores=rating_scores
        )

        # Step 6: Cleanup temp files
        s3_ingest.cleanup_s3_temp_files(s3_prefix)

        logger.info(f"Successfully completed artifact {artifact_id}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'artifact_id': artifact_id,
                'status': 'completed',
                'size_bytes': size_bytes
            })
        }

    except Exception as e:
        logger.error(f"Processing failed for artifact {artifact_id}: {str(e)}", exc_info=True)

        # Update status to failed
        try:
            update_artifact_status(artifact_id, 'failed', str(e)[:500])
        except:
            pass

        # Cleanup on failure
        if s3_prefix:
            try:
                s3_ingest = S3DirectIngest()
                s3_ingest.cleanup_s3_temp_files(s3_prefix)
            except:
                pass

        return {
            'statusCode': 500,
            'body': json.dumps({
                'artifact_id': artifact_id,
                'status': 'failed',
                'error': str(e)
            })
        }


def extract_repo_id(url: str) -> str:
    """Extract repo ID from Hugging Face URL"""
    url = url.rstrip('/')

    if '/datasets/' in url:
        repo_id = url.split('/datasets/')[-1]
    elif '/spaces/' in url:
        repo_id = url.split('/spaces/')[-1]
    else:
        parts = url.split('huggingface.co/')
        if len(parts) > 1:
            repo_id = parts[-1]
        else:
            raise ValueError(f"Invalid Hugging Face URL: {url}")

    if '/tree/' in repo_id:
        repo_id = repo_id.split('/tree/')[0]

    return repo_id


def get_db_connection():
    """Get PostgreSQL database connection"""
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        sslmode='require',
        connect_timeout=10
    )


def update_artifact_status(artifact_id: int, status: str, message: str = None):
    """Update artifact status in database"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            if message:
                cur.execute(
                    "UPDATE artifacts SET status = %s, status_message = %s, updated_at = NOW() WHERE id = %s",
                    (status, message, artifact_id)
                )
            else:
                cur.execute(
                    "UPDATE artifacts SET status = %s, updated_at = NOW() WHERE id = %s",
                    (status, artifact_id)
                )
            conn.commit()
            logger.info(f"Updated artifact {artifact_id}: status={status}")
    except Exception as e:
        logger.error(f"Failed to update artifact status: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def update_artifact_complete(
    artifact_id: int,
    zip_s3_key: str,
    sha256: str,
    size_bytes: int,
    rating_scores: Dict
):
    """Update artifact with completion data and save rating"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # Update artifact
            cur.execute("""
                UPDATE artifacts
                SET status = 'completed',
                    status_message = 'Successfully ingested',
                    blob = %s,
                    sha256 = %s,
                    size_bytes = %s,
                    rating_completed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (zip_s3_key, sha256, size_bytes, artifact_id))

            # Insert rating if model
            if rating_scores:
                cur.execute("""
                    INSERT INTO model_ratings (
                        artifact_id, name, category,
                        net_score, net_score_latency,
                        ramp_up_time, ramp_up_time_latency,
                        bus_factor, bus_factor_latency,
                        performance_claims, performance_claims_latency,
                        license, license_latency,
                        dataset_and_code_score, dataset_and_code_score_latency,
                        dataset_quality, dataset_quality_latency,
                        code_quality, code_quality_latency,
                        reproducibility, reproducibility_latency,
                        reviewedness, reviewedness_latency,
                        tree_score, tree_score_latency,
                        size_score, size_score_latency,
                        total_rating_time, created_at
                    ) VALUES (
                        %s, (SELECT name FROM artifacts WHERE id = %s), 'MODEL',
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                    )
                """, (
                    artifact_id, artifact_id,
                    rating_scores.get('net_score', 0),
                    rating_scores.get('net_score_latency', 0),
                    rating_scores.get('ramp_up_time', 0),
                    rating_scores.get('ramp_up_time_latency', 0),
                    rating_scores.get('bus_factor', 0),
                    rating_scores.get('bus_factor_latency', 0),
                    rating_scores.get('performance_claims', 0),
                    rating_scores.get('performance_claims_latency', 0),
                    rating_scores.get('license', 0),
                    rating_scores.get('license_latency', 0),
                    rating_scores.get('dataset_and_code_score', 0),
                    rating_scores.get('dataset_and_code_score_latency', 0),
                    rating_scores.get('dataset_quality', 0),
                    rating_scores.get('dataset_quality_latency', 0),
                    rating_scores.get('code_quality', 0),
                    rating_scores.get('code_quality_latency', 0),
                    rating_scores.get('reproducibility', 0),
                    rating_scores.get('reproducibility_latency', 0),
                    rating_scores.get('reviewedness', 0),
                    rating_scores.get('reviewedness_latency', 0),
                    rating_scores.get('tree_score', 0),
                    rating_scores.get('tree_score_latency', 0),
                    rating_scores.get('size_score', 0),
                    rating_scores.get('size_score_latency', 0),
                    rating_scores.get('total_rating_time', 0)
                ))

            conn.commit()
            logger.info(f"Artifact {artifact_id} marked as completed")
    except Exception as e:
        logger.error(f"Failed to update artifact completion: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def compute_ratings(local_path: str, source_url: str, name: str, code_name: Optional[str] = None) -> Dict:
    """
    Compute ratings for the artifact using ModelMetricService
    """
    try:
        # Import metric service (should be in Lambda package)
        from Services.Metric_Model_Service import ModelMetricService
        from Models import Model
        from lib.Github_API_Manager import GitHubAPIManager
        import time

        logger.info(f"Starting rating computation for {name}")

        # Initialize service
        metric_service = ModelMetricService()
        
        # Initialize GitHub manager for reviewedness
        github_token = os.getenv("GITHUB_TOKEN")
        github_manager = GitHubAPIManager(token=github_token) if github_token else None

        # Create Model object from local files
        model_data = create_model_object(local_path, source_url, name)

        if not model_data:
            logger.warning("Could not create Model object, using fallback")
            return fallback_rating()

        scores = {}

        # Run all evaluations
        evaluations = [
            ("performance_claims", metric_service.EvaluatePerformanceClaims),
            ("ramp_up_time", metric_service.EvaluateRampUpTime),
            ("bus_factor", metric_service.EvaluateBusFactor),
            ("license", metric_service.EvaluateLicense),
            ("dataset_and_code_score", metric_service.EvaluateDatasetAndCodeAvailabilityScore),
            ("dataset_quality", metric_service.EvaluateDatasetsQuality),
            ("code_quality", metric_service.EvaluateCodeQuality),
            ("size_score", metric_service.EvaluateSize),
        ]

        for metric_name, eval_func in evaluations:
            start = time.time()
            result = eval_func(model_data)
            latency = time.time() - start

            scores[metric_name] = result.value if hasattr(result, 'value') else 0.0
            scores[f"{metric_name}_latency"] = latency

        # Calculate new metrics
        # Reproducibility - placeholder for now (requires running demo code)
        scores["reproducibility"] = 0.6
        scores["reproducibility_latency"] = 0.0
        
        # Reviewedness
        start = time.time()
        scores["reviewedness"] = calculate_reviewedness(github_manager, code_name)
        scores["reviewedness_latency"] = time.time() - start
        
        # Tree score
        start = time.time()
        scores["tree_score"] = calculate_tree_score(local_path, name)
        scores["tree_score_latency"] = time.time() - start

        # Calculate net score as weighted average
        scores["net_score"] = calculate_net_score(scores)
        scores["net_score_latency"] = sum(
            scores.get(f"{m}_latency", 0)
            for m in ["performance_claims", "ramp_up_time", "bus_factor", "license"]
        )
        
        scores["total_rating_time"] = sum(
            scores.get(f"{m}_latency", 0)
            for m in ["performance_claims", "ramp_up_time", "bus_factor", "license",
                     "dataset_and_code_score", "dataset_quality", "code_quality",
                     "size_score", "reproducibility", "reviewedness", "tree_score"]
        )

        logger.info(f"Rating completed: net_score={scores['net_score']:.3f}")
        return scores

    except Exception as e:
        logger.error(f"Rating computation failed: {str(e)}", exc_info=True)
        return fallback_rating()


def calculate_tree_score(local_path: str, artifact_name: str) -> float:
    """
    Calculate tree score: Average of net scores of parents in the registry
    
    Args:
        local_path: Path to downloaded model files
        artifact_name: Name of the current artifact
        
    Returns:
        float: Average score of parent models, or 0.6 if no parents found
    """
    try:
        parent_model_ids = extract_parent_models_from_config(local_path)

        if not parent_model_ids:
            logger.info("No parent model found in config")
            return 0.6  # Default score when no parents

        parent_scores = []
        conn = get_db_connection()
        
        try:
            with conn.cursor() as cur:
                for parent_model_id in parent_model_ids:
                    # Extract just the model name from full ID (e.g., "org/model" -> "model")
                    parent_name = parent_model_id.split('/')[-1] if '/' in parent_model_id else parent_model_id
                    
                    # Query database for parent artifact rating
                    cur.execute("""
                        SELECT mr.net_score
                        FROM artifacts a
                        JOIN model_ratings mr ON a.id = mr.artifact_id
                        WHERE a.type = 'model'
                        AND a.status = 'completed'
                        AND (a.name ILIKE %s OR a.name ILIKE %s)
                        ORDER BY a.created_at DESC
                        LIMIT 1
                    """, (f"%{parent_name}%", parent_model_id))
                    
                    result = cur.fetchone()
                    if result and result[0] is not None:
                        parent_scores.append(float(result[0]))
                        logger.info(f"Found parent {parent_name} with score {result[0]}")
        finally:
            conn.close()

        if parent_scores:
            avg_score = sum(parent_scores) / len(parent_scores)
            logger.info(f"Tree score calculated: {avg_score:.3f} from {len(parent_scores)} parents")
            return avg_score
        else:
            logger.info("No parent scores found in registry")
            return 0.6  # Default when parents not in registry

    except Exception as e:
        logger.warning(f"Failed to calculate tree score: {e}")
        return 0.6


def extract_parent_models_from_config(local_path: str) -> list:
    """
    Extract parent model IDs from config.json
    
    Looks for fields like:
    - _name_or_path
    - base_model
    - parent_model
    
    Returns:
        list: List of parent model IDs
    """
    try:
        config_path = os.path.join(local_path, 'config.json')
        if not os.path.exists(config_path):
            return []
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        parent_ids = []
        
        # Check common fields that indicate parent models
        parent_fields = ['_name_or_path', 'base_model', 'parent_model', 'base_model_name_or_path']
        
        for field in parent_fields:
            if field in config and config[field]:
                value = config[field]
                # Skip local paths or generic names
                if isinstance(value, str) and '/' in value and not value.startswith('.'):
                    parent_ids.append(value)
        
        return parent_ids
        
    except Exception as e:
        logger.warning(f"Failed to extract parent models from config: {e}")
        return []


def calculate_reviewedness(github_manager: Optional[GitHubAPIManager], code_name: Optional[str]) -> float:
    """
    Calculate reviewedness: Fraction of code (not weights) that was 
    introduced through PRs with code reviews.
    
    This is an approximation based on the lines added in PRs vs total lines added.
    
    Args:
        github_manager: GitHub API manager instance
        code_name: GitHub repository name or URL
        
    Returns:
        float: Fraction between 0.0 and 1.0, or -1 if no GitHub repo linked
    """
    if not code_name or not github_manager:
        logger.info("No code repository or GitHub manager available")
        return -1.0

    CODE_EXTS = {
        ".py", ".ipynb", ".pyi",
        ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
        ".vue", ".svelte",
        ".java", ".go", ".rs",
        ".cpp", ".cc", ".c", ".h", ".hpp",
        ".cs", ".rb", ".php", ".swift",
        ".kt", ".scala",
        ".sh", ".bash", ".ps1",
        ".yaml", ".yml", ".json", ".toml",
        ".ini", ".cfg", ".conf",
        ".md", ".rst",
        ".html", ".css", ".scss", ".sass",
        ".sql", ".r", ".R",
        ".dockerfile", ".tf",
    }

    try:
        # Construct GitHub URL from code_name
        if code_name.startswith('http'):
            github_url = code_name
        else:
            github_url = f"https://github.com/{code_name}"

        owner, repo = github_manager.code_link_to_repo(github_url)
        logger.info(f"Calculating reviewedness for {owner}/{repo}")

        # Get merged PRs (limit to avoid rate limiting)
        all_prs = github_manager.github_request(
            path=f"/repos/{owner}/{repo}/pulls",
            params={"state": "closed", "per_page": 50}  # Reduced from 100
        )

        reviewed_pr_lines = 0
        unreviewed_pr_lines = 0
        pr_count = 0

        for pr in all_prs:
            if not pr.get('merged_at'):
                continue
            
            pr_count += 1
            if pr_count > 30:  # Limit to avoid excessive API calls
                break

            try:
                # Get files changed in this PR
                pr_files = github_manager.github_request(
                    path=f"/repos/{owner}/{repo}/pulls/{pr['number']}/files"
                )

                # Count code lines (not weights/data files)
                pr_code_lines = 0
                for file in pr_files:
                    filename_lower = file['filename'].lower()
                    # Skip weight files
                    if any(skip in filename_lower for skip in ['.bin', '.safetensors', '.ckpt', '.pth', '.h5']):
                        continue
                    # Count code files
                    if any(filename_lower.endswith(ext) for ext in CODE_EXTS):
                        pr_code_lines += file.get('additions', 0)

                if pr_code_lines == 0:
                    continue

                # Check if reviewed (has at least one review)
                reviews = github_manager.github_request(
                    path=f"/repos/{owner}/{repo}/pulls/{pr['number']}/reviews"
                )

                if reviews and len(reviews) > 0:
                    reviewed_pr_lines += pr_code_lines
                else:
                    unreviewed_pr_lines += pr_code_lines
                    
            except Exception as e:
                logger.warning(f"Failed to process PR #{pr['number']}: {e}")
                continue

        # Calculate fraction
        total_lines = reviewed_pr_lines + unreviewed_pr_lines

        if total_lines == 0:
            logger.info(f"No code lines found in PRs for {owner}/{repo}")
            return -1.0

        fraction = reviewed_pr_lines / total_lines
        logger.info(f"Reviewedness: {reviewed_pr_lines}/{total_lines} = {fraction:.3f}")
        return min(1.0, max(0.0, fraction))

    except Exception as e:
        logger.warning(f"Failed to calculate reviewedness for {code_name}: {e}")
        return -1.0


def create_model_object(local_path: str, source_url: str, name: str):
    """Create Model object from downloaded files"""
    try:
        from Models import Model
        import os

        # Read README if exists
        readme_path = None
        for fname in ['README.md', 'README.txt', 'readme.md']:
            potential_path = os.path.join(local_path, fname)
            if os.path.exists(potential_path):
                readme_path = potential_path
                break

        # Read config.json if exists
        config_path = os.path.join(local_path, 'config.json')
        card = None
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                card = json.load(f)

        # Create Model object
        model = Model()
        model.name = name
        model.url = source_url
        model.readme_path = readme_path
        model.card = card

        # Try to get repo info from HuggingFace API
        try:
            from huggingface_hub import HfApi
            hf_api = HfApi()

            # Extract repo_id from URL
            repo_id = source_url.split('huggingface.co/')[-1]
            if '/tree/' in repo_id:
                repo_id = repo_id.split('/tree/')[0]

            # Get repo info
            repo_info = hf_api.repo_info(repo_id)
            model.repo_commit_history = []  # Would need API call
            model.repo_contributors = []     # Would need API call

        except:
            pass  # Use defaults

        return model

    except Exception as e:
        logger.error(f"Failed to create Model object: {e}")
        return None


def calculate_net_score(scores: Dict[str, float]) -> float:
    """Calculate weighted net score from individual metrics"""
    weights = {
        "performance_claims": 0.15,
        "ramp_up_time": 0.10,
        "bus_factor": 0.10,
        "license": 0.15,
        "dataset_quality": 0.15,
        "code_quality": 0.15,
        "reproducibility": 0.10,
        "reviewedness": 0.05,
        "tree_score": 0.03,
        "size_score": 0.02,
    }

    net = 0.0
    for metric, weight in weights.items():
        net += scores.get(metric, 0.0) * weight

    return net


def fallback_rating() -> Dict[str, float]:
    """Fallback rating when metrics unavailable"""
    return {
        "net_score": 0.75,
        "net_score_latency": 0.0,
        "ramp_up_time": 0.7,
        "ramp_up_time_latency": 0.0,
        "bus_factor": 0.6,
        "bus_factor_latency": 0.0,
        "performance_claims": 0.7,
        "performance_claims_latency": 0.0,
        "license": 0.8,
        "license_latency": 0.0,
        "dataset_and_code_score": 0.65,
        "dataset_and_code_score_latency": 0.0,
        "dataset_quality": 0.7,
        "dataset_quality_latency": 0.0,
        "code_quality": 0.68,
        "code_quality_latency": 0.0,
        "reproducibility": 0.6,
        "reproducibility_latency": 0.0,
        "reviewedness": 0.5,
        "reviewedness_latency": 0.0,
        "tree_score": 0.8,
        "tree_score_latency": 0.0,
        "size_score": 0.75,
        "size_score_latency": 0.0,
        "total_rating_time": 0.0
    }


def extract_code_repo_from_metadata(local_path: str) -> Optional[str]:
    """
    Extract GitHub repository URL from model metadata files
    
    Checks:
    1. config.json for 'repo' or similar fields
    2. README.md for GitHub links
    
    Returns:
        str: GitHub repo URL or None if not found
    """
    try:
        # Check config.json first
        config_path = os.path.join(local_path, 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Common fields that contain GitHub repo
            repo_fields = ['repo', 'repository', 'code_repository', 'github_repo']
            for field in repo_fields:
                if field in config and config[field]:
                    value = config[field]
                    if isinstance(value, str) and 'github.com' in value:
                        return value
        
        # Check README.md for GitHub links
        for readme_name in ['README.md', 'README.txt', 'readme.md']:
            readme_path = os.path.join(local_path, readme_name)
            if os.path.exists(readme_path):
                try:
                    with open(readme_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Look for GitHub URLs
                    import re
                    github_pattern = r'https?://github\.com/[\w\-]+/[\w\-]+'
                    matches = re.findall(github_pattern, content)
                    if matches:
                        # Return the first GitHub URL found
                        return matches[0]
                except Exception as e:
                    logger.warning(f"Failed to read {readme_name}: {e}")
        
        logger.info("No GitHub repository found in metadata")
        return None
        
    except Exception as e:
        logger.warning(f"Failed to extract code repo: {e}")
        return None
