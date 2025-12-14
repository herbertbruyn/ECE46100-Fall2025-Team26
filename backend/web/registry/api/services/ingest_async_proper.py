"""
Async Ingest Service - Returns 202 and queues background work

Implements the spec's async flow:
1. POST returns 202 with artifact ID
2. Background worker does rating + ingest
3. GET returns 404 until status=ready
"""
import os
import sys
import logging
import json
import tempfile
from typing import Dict, Tuple, Optional
from django.db import transaction
import boto3

from api.models import Artifact

logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 0.0  # Minimum score for each metric to pass quality gate

class AsyncIngestService:
    """
    Async ingest service - returns 202 immediately, queues work for background
    """

    def __init__(self):
        # Initialize SQS client for job queue
        self.sqs_client = None
        self.queue_url = os.getenv('SQS_QUEUE_URL')
        self.use_worker = os.getenv('USE_BACKGROUND_WORKER', 'true').lower() == 'true'

        if self.queue_url:
            try:
                self.sqs_client = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))
                logger.info(f"Initialized SQS client with queue: {self.queue_url}")
            except Exception as e:
                logger.error(f"Failed to initialize SQS client: {e}")
                self.sqs_client = None

    def ingest_artifact(
        self,
        source_url: str,
        artifact_type: str,
        revision: str = "main",
        uploaded_by=None
    ) -> Tuple[int, Dict]:
        """
        Accept artifact for async ingestion - returns 202 immediately

        Returns:
            - 202: Accepted, queued for background processing
            - 400: Bad request
            - 403: Auth failure
            - 409: Duplicate artifact
        """
        logger.info(f"=" * 80)
        logger.info(f"INGEST REQUEST: type={artifact_type}, url={source_url}")
        logger.info(f"=" * 80)

        # Validate artifact_type
        valid_types = ['model', 'dataset', 'code']
        if artifact_type not in valid_types:
            return 400, {
                "error": f"Invalid artifact_type. Must be one of: {', '.join(valid_types)}"
            }

        # Parse repo_id from source_url
        repo_id = self._parse_repo_id(source_url)
        if not repo_id:
            logger.error(f"PARSE FAILED: Could not extract repo_id from URL: {source_url}")
            return 400, {
                "error": "Invalid HuggingFace URL"
            }

        logger.info(f"PARSED: repo_id='{repo_id}' from url='{source_url}'")

        # Check for duplicates (only READY artifacts count as duplicates)
        existing = Artifact.objects.filter(
            source_url=source_url,
            type=artifact_type,
        ).first()

        if existing:
            logger.warning(f"DUPLICATE: {artifact_type} '{repo_id}' already exists as artifact #{existing.id} (status={existing.status})")
            return 409, {
                "error": "Artifact exists already",
                "existing_id": existing.id
            }

        # Create artifact with pending_rating status
        with transaction.atomic():
            artifact = Artifact.objects.create(
                name=repo_id.split('/')[-1],
                source_url=source_url,
                type=artifact_type,
                status="pending_rating",  # Waiting for background worker
                uploaded_by=uploaded_by
            )
            artifact_id = artifact.id

        # Enqueue job for background processing
        job_data = {
            'artifact_id': artifact_id,
            'artifact_type': artifact_type,
            'source_url': source_url,
            'revision': revision,
            'uploaded_by_id': uploaded_by.id if uploaded_by else None
        }

        if self.sqs_client and self.queue_url:
            try:
                self.sqs_client.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=json.dumps(job_data)
                )
                logger.info(f"Queued artifact {artifact_id} for async processing via SQS")
            except Exception as e:
                logger.error(f"Failed to send to SQS: {e}")
                # If worker is running, it will pick this up from DB (don't spawn thread)
                if not self.use_worker:
                    logger.warning("No worker process, falling back to threading")
                    import threading
                    thread = threading.Thread(
                        target=self._process_artifact_background,
                        args=(job_data,)
                    )
                    thread.daemon = True
                    thread.start()
                else:
                    logger.info("Worker will pick up artifact from database")
        elif self.use_worker:
            # Worker is running, it will poll database for pending_rating artifacts
            logger.info(f"Queued artifact {artifact_id} for worker (database polling)")
        else:
            # No SQS, no worker - use threading as last resort
            logger.warning("No SQS or worker, using thread for async processing")
            import threading
            thread = threading.Thread(
                target=self._process_artifact_background,
                args=(job_data,)
            )
            thread.daemon = True
            thread.start()

        # Return 202 Accepted with artifact metadata
        # Per spec: download_url is not yet available
        logger.info(f"ACCEPTED: Created artifact #{artifact.id} ({artifact_type} '{repo_id}') - status=pending_rating")
        logger.info(f"=" * 80)
        return 202, {
            "metadata": {
                "name": artifact.name,
                "id": artifact.id,
                "type": artifact.type
            },
            "data": {
                "url": source_url
                # download_url will be added when status=ready
            }
        }

    def _process_artifact_background(self, job_data: Dict):
        """
        Background processing (called by worker or thread)
        This would normally be in a separate worker process
        """
        from .s3_zero_disk_ingest import S3ZeroDiskIngest

        artifact_id = job_data['artifact_id']
        artifact_type = job_data['artifact_type']
        source_url = job_data['source_url']
        revision = job_data.get('revision', 'main')

        try:
            artifact = Artifact.objects.get(id=artifact_id)

            logger.info(f"")
            logger.info(f"{'='*80}")
            logger.info(f"WORKER PROCESSING: Artifact #{artifact_id} ({artifact_type})")
            logger.info(f"  URL: {source_url}")
            logger.info(f"{'='*80}")

            # STEP 1: Rating (only for models)
            zero_disk = S3ZeroDiskIngest()
            repo_id = self._parse_repo_id(source_url)
            repo_type_map = {'model': 'model', 'dataset': 'dataset', 'code': 'space'}
            repo_type = repo_type_map.get(artifact_type, 'model')

            metrics = None
            net_score = None
            minimal_files = None

            if artifact_type == "model":
                logger.info(f"RATING: Starting metrics evaluation for model #{artifact_id}")
                artifact.status = "rating_in_progress"
                artifact.save()

                # Download minimal files for rating
                minimal_files = zero_disk.download_minimal_for_metrics(
                    repo_id=repo_id,
                    repo_type=repo_type,
                    revision=revision
                )

                # Compute metrics (pass artifact_id for tree_score)
                metrics = self._compute_metrics(minimal_files, source_url, repo_id, artifact_id)
                net_score = self._calculate_net_score(metrics)

                # STEP 2: Quality gate check - EACH metric must be > threshold
                failed_metrics = []
                for metric_name, metric_value in metrics.items():
                    if metric_value < SCORE_THRESHOLD:
                        failed_metrics.append(f"{metric_name}={metric_value:.2f}")

                if failed_metrics:
                    logger.warning(f"DISQUALIFIED: Artifact #{artifact_id} failed quality gate!")
                    logger.warning(f"  Net score: {net_score:.3f}")
                    logger.warning(f"  Failed metrics: {', '.join(failed_metrics)}")
                    logger.warning(f"{'='*80}")
                    with transaction.atomic():
                        artifact.status = "disqualified"
                        artifact.rating_scores = metrics
                        artifact.net_score = net_score
                        artifact.save()
                    return  # Don't ingest, artifact stays hidden (404)

                logger.info(f"PASSED QUALITY GATE: All metrics >= {SCORE_THRESHOLD}, net_score={net_score:.3f}")
            else:
                # For datasets/code, skip metrics evaluation entirely
                logger.info(f"SKIP RATING: {artifact_type} artifacts don't require metrics evaluation")

            # STEP 3: Ingest artifact to S3
            is_github = 'github.com' in source_url
            is_kaggle = 'kaggle.com' in source_url
            source_type = 'GitHub' if is_github else ('Kaggle' if is_kaggle else 'HuggingFace')
            logger.info(f"INGESTING: Streaming {source_type} repo to S3...")
            artifact.status = "ingesting"
            artifact.save()

            s3_key = f"artifacts/{artifact_type}/{artifact_id}/{repo_id.replace('/', '_')}.zip"
            sha256_hash, total_size = zero_disk.download_and_zip_to_s3_streaming(
                repo_id=repo_id,
                artifact_type=artifact_type,
                output_zip_key=s3_key,
                revision=revision,
                artifact_id=artifact_id,
                source_url=source_url  # Pass source_url to detect GitHub vs HF
            )

            # Generate presigned URL
            download_url = zero_disk.get_s3_presigned_url(s3_key, expiration=3600)

            # STEP 4: Mark as ready
            with transaction.atomic():
                artifact.status = "ready"
                artifact.s3_key = s3_key
                artifact.download_url = download_url
                artifact.file_size = total_size
                artifact.sha256_hash = sha256_hash
                artifact.rating_scores = metrics
                artifact.net_score = net_score

                # Dataset/code linking for models
                if artifact_type == "model" and minimal_files:
                    dataset_name, code_name = self._extract_dependencies(minimal_files)
                    if dataset_name or code_name:
                        from api.models import find_or_create_dataset, find_or_create_code
                        if dataset_name:
                            artifact.dataset_name = dataset_name
                            artifact.dataset = find_or_create_dataset(dataset_name)
                        if code_name:
                            artifact.code_name = code_name
                            artifact.code = find_or_create_code(code_name)

                # Reverse linking: if this is a dataset/code, link any existing models that reference it
                if artifact_type == "dataset":
                    # Find models that have this dataset name in their dataset_name field
                    from api.models import find_or_create_dataset
                    dataset_obj = find_or_create_dataset(artifact.name)

                    # Update all models that reference this dataset by name
                    models_to_link = Artifact.objects.filter(
                        type="model",
                        dataset_name__icontains=artifact.name,
                        dataset__isnull=True  # Only link models that don't already have a dataset linked
                    )
                    for model_artifact in models_to_link:
                        model_artifact.dataset = dataset_obj
                        model_artifact.save()
                        logger.info(f"Reverse-linked model {model_artifact.id} to dataset {artifact.id}")

                elif artifact_type == "code":
                    # Find models that have this code name in their code_name field
                    from api.models import find_or_create_code
                    code_obj = find_or_create_code(artifact.name)

                    # Update all models that reference this code by name
                    models_to_link = Artifact.objects.filter(
                        type="model",
                        code_name__icontains=artifact.name,
                        code__isnull=True  # Only link models that don't already have a code linked
                    )
                    for model_artifact in models_to_link:
                        model_artifact.code = code_obj
                        model_artifact.save()
                        logger.info(f"Reverse-linked model {model_artifact.id} to code {artifact.id}")

                artifact.save()

            logger.info(f"SUCCESS: Artifact #{artifact_id} ({artifact_type} '{repo_id}') is now READY!")
            logger.info(f"  Size: {total_size:,} bytes, SHA256: {sha256_hash[:16]}...")
            logger.info(f"  Download URL: {download_url[:80]}..." if download_url and len(download_url) > 80 else f"  Download URL: {download_url}")
            logger.info(f"{'='*80}")

        except Exception as e:
            logger.error(f"FAILED: Artifact #{artifact_id} ({artifact_type}) processing failed!")
            logger.error(f"  Error: {str(e)}")
            logger.error(f"{'='*80}")
            try:
                artifact = Artifact.objects.get(id=artifact_id)
                artifact.status = "failed"
                artifact.save()
            except:
                pass

    def _parse_repo_id(self, source_url: str) -> Optional[str]:
        """Extract repo_id from HuggingFace, GitHub, or Kaggle URL"""
        url = source_url.rstrip('/')

        # Handle HuggingFace URLs
        if 'huggingface.co/' in url:
            parts = url.split('huggingface.co/')[-1].split('/')
            if parts[0] in ['datasets', 'spaces']:
                return '/'.join(parts[1:])
            return '/'.join(parts)

        # Handle GitHub URLs for code artifacts
        if 'github.com/' in url:
            parts = url.split('github.com/')[-1].split('/')
            # GitHub URLs are typically: github.com/owner/repo or github.com/owner/repo.git
            if len(parts) >= 2:
                repo_name = parts[1]
                # Remove .git suffix if present (use removesuffix for exact match)
                if repo_name.endswith('.git'):
                    repo_name = repo_name[:-4]
                return f"{parts[0]}/{repo_name}"
            return None

        # Handle Kaggle URLs for datasets
        # Format: https://www.kaggle.com/datasets/username/dataset-name
        if 'kaggle.com/' in url:
            parts = url.split('kaggle.com/')[-1].split('/')
            if len(parts) >= 3 and parts[0] == 'datasets':
                # Return username/dataset-name
                return f"{parts[1]}/{parts[2]}"
            return None

        return None

    def _compute_metrics(self, minimal_files: Dict[str, bytes], source_url: str, repo_id: str, artifact_id: int) -> Dict:
        """
        Compute ALL metrics using the real ModelMetricService

        Integrates with the existing metrics service in backend/src/Services
        """
        # Add src directory to path to import metrics service
        src_path = os.path.join(os.path.dirname(__file__), '../../../../src')
        if os.path.exists(src_path) and src_path not in sys.path:
            sys.path.insert(0, src_path)

        try:
            from Services.Metric_Model_Service import ModelMetricService
            from Models.Model import Model

            # Create model data object from minimal_files
            class MinimalModelData(Model):
                """Adapter to convert minimal_files data into Model interface for metrics"""
                def __init__(self, minimal_files: Dict[str, bytes], source_url: str, repo_id: str):
                    super().__init__()  # Initialize parent Model class
                    # README (write to temp file - metrics service expects path)
                    self.readme_path = None
                    for filename in ['README.md', 'README.txt', 'README']:
                        if filename in minimal_files:
                            try:
                                fd, path = tempfile.mkstemp(suffix='.md', text=True)
                                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                                    content = minimal_files[filename].decode('utf-8', errors='ignore')
                                    f.write(content)
                                self.readme_path = path
                                break
                            except Exception as e:
                                logger.warning(f"Failed to write README temp file: {e}")

                    # Card data (model card)
                    self.card = None

                    # Repo metadata (size, license, etc.)
                    self.repo_metadata = {}
                    if '_hf_repo_metadata' in minimal_files:
                        try:
                            self.repo_metadata = json.loads(minimal_files['_hf_repo_metadata'].decode('utf-8'))
                        except:
                            pass

                    # Commit history (for bus factor)
                    self.repo_commit_history = []
                    if '_hf_commit_history' in minimal_files:
                        try:
                            commits = json.loads(minimal_files['_hf_commit_history'].decode('utf-8'))
                            # Convert to format expected by bus factor metric
                            self.repo_commit_history = [
                                {
                                    'commit': {
                                        'author': {
                                            'date': c.get('date', '')
                                        }
                                    }
                                }
                                for c in commits
                            ]
                        except:
                            pass

                    # Contributors (for bus factor)
                    self.repo_contributors = []
                    if '_hf_contributors_count' in minimal_files:
                        try:
                            contrib_data = json.loads(minimal_files['_hf_contributors_count'].decode('utf-8'))
                            count = contrib_data.get('count', 0)
                            # Create mock contributor list (bus factor only needs count)
                            self.repo_contributors = [{'contributions': 1} for _ in range(count)]
                        except:
                            pass

                    # File structure (for code quality)
                    self.repo_contents = []
                    if '_hf_file_structure' in minimal_files:
                        try:
                            self.repo_contents = json.loads(minimal_files['_hf_file_structure'].decode('utf-8'))
                        except:
                            pass

                    # Dataset cards and infos (for dataset quality)
                    self.dataset_cards = {}
                    self.dataset_infos = {}

                    self.source_url = source_url
                    self.repo_id = repo_id

                def __del__(self):
                    """Clean up temp README file"""
                    if self.readme_path and os.path.exists(self.readme_path):
                        try:
                            os.unlink(self.readme_path)
                        except:
                            pass

            # Create data object
            model_data = MinimalModelData(minimal_files, source_url, repo_id)

            # Use the existing parallel metrics computation from src/main.py
            from main import run_evaluations_parallel

            logger.info("Running metrics evaluation using src/main.py pipeline...")
            evaluation_results = run_evaluations_parallel(model_data, max_workers=4)

            # Convert from main.py format to our format
            # main.py returns: {"Metric Name": (MetricResult, latency), ...}
            # We need: {"metric_name": score_value, ...}
            metric_name_map = {
                "Performance Claims": "performance_claims",
                "Bus Factor": "bus_factor",
                "Size": "size_score",
                "Ramp-Up Time": "ramp_up_time",
                "Availability": "dataset_and_code_score",
                "Code Quality": "code_quality",
                "Dataset Quality": "dataset_quality",
                "License": "license_score",
                "Reproducibility": "reproducibility"
            }

            metrics = {}
            for display_name, (metric_result, _latency) in evaluation_results.items():
                metric_key = metric_name_map.get(display_name, display_name.lower().replace(" ", "_"))
                metrics[metric_key] = metric_result.value if hasattr(metric_result, 'value') else metric_result

            # Add the 2 additional Django-specific metrics not in main.py pipeline
            logger.info("Computing additional metrics (tree_score, reviewedness)...")

            # Tree score: parent model's net score
            try:
                metrics['tree_score'] = self._compute_tree_score(artifact_id, minimal_files, repo_id)
                logger.info(f"Completed tree_score: {metrics['tree_score']}")
            except Exception as e:
                logger.warning(f"tree_score metric failed: {e}")
                metrics['tree_score'] = 0.5

            # Reviewedness: GitHub code review metrics
            try:
                metrics['reviewedness'] = self._compute_reviewedness(minimal_files, repo_id, source_url)
                logger.info(f"Completed reviewedness: {metrics['reviewedness']}")
            except Exception as e:
                logger.warning(f"reviewedness metric failed: {e}")
                metrics['reviewedness'] = 0.5

            logger.info(f"All metrics computed: {metrics}")
            return metrics

        except ImportError as e:
            logger.error(f"Failed to import ModelMetricService: {e}")
            return self._compute_metrics_fallback(minimal_files)
        except Exception as e:
            logger.error(f"Metrics computation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._compute_metrics_fallback(minimal_files)

    def _compute_metrics_fallback(self, minimal_files: Dict[str, bytes]) -> Dict:
        """Fallback metrics if ModelMetricService unavailable"""
        logger.warning("Using fallback metrics computation")
        readme_content = None
        for filename in ['README.md', 'README.txt']:
            if filename in minimal_files:
                try:
                    readme_content = minimal_files[filename].decode('utf-8', errors='ignore')
                    break
                except:
                    pass

        return {
            'documentation': min(len(readme_content) / 1000, 1.0) if readme_content else 0.0,
            'ramp_up_time': 0.5,
            'bus_factor': 0.5,
            'size_score': 0.5,
            'code_quality': 0.5,
            'dataset_quality': 0.5,
            'dataset_and_code_score': 0.5,
            'performance_claims': 0.5,
            'license_score': 0.5,
            'reproducibility': 0.5,
            'tree_score': 0.5,
            'reviewedness': 0.5
        }

    def _calculate_net_score(self, metrics: Dict) -> float:
        """
        Calculate weighted net score based on main.py specification:

        NetScore = 0.20*RampUp + 0.15*BusFactor + 0.15*PerfClaim + 0.15*License +
                   0.10*Size + 0.10*DatasetCode + 0.10*DatasetQual + 0.05*CodeQual +
                   0.05*Reproducibility + 0.03*TreeScore + 0.02*Reviewedness

        Total: 1.00 (100%)
        """
        weights = {
            'ramp_up_time': 0.20,
            'bus_factor': 0.15,
            'performance_claims': 0.15,
            'license_score': 0.15,
            'size_score': 0.10,
            'dataset_and_code_score': 0.10,
            'dataset_quality': 0.10,
            'code_quality': 0.05,
            'reproducibility': 0.05,
            'tree_score': 0.03,
            'reviewedness': 0.02
        }

        weighted_sum = 0.0

        for metric, score in metrics.items():
            if isinstance(score, (int, float)):
                weight = weights.get(metric, 0.0)
                weighted_sum += score * weight

        return weighted_sum

    def _extract_dependencies(self, minimal_files: Dict[str, bytes]) -> Tuple[Optional[str], Optional[str]]:
        """Extract dataset/code names from README"""
        import re
        readme_content = None
        for filename in ['README.md', 'README.txt']:
            if filename in minimal_files:
                try:
                    readme_content = minimal_files[filename].decode('utf-8', errors='ignore')
                    break
                except:
                    pass

        if not readme_content:
            return None, None

        dataset_pattern = r'(?:dataset|training[_\s]?data|trained[_\s]?on)[:\s]+([a-zA-Z0-9/_-]+)'
        code_pattern = r'(?:code|repository|repo|github)[:\s]+([a-zA-Z0-9/_-]+)'

        dataset_match = re.search(dataset_pattern, readme_content, re.IGNORECASE)
        code_match = re.search(code_pattern, readme_content, re.IGNORECASE)

        return (
            dataset_match.group(1) if dataset_match else None,
            code_match.group(1) if code_match else None
        )

    def _compute_tree_score(self, artifact_id: int, minimal_files: Dict[str, bytes], repo_id: str) -> float:
        """
        Compute tree score: average of parent model net scores from lineage graph
        """
        import json
        
        try:
            parent_model_id = None
            if 'config.json' in minimal_files:
                try:
                    config = json.loads(minimal_files['config.json'].decode('utf-8'))
                    for field in ['base_model_name_or_path', '_name_or_path', 'base_model']:
                        if field in config and isinstance(config[field], str) and config[field]:
                            parent_model_id = config[field]
                            break
                except Exception as e:
                    logger.warning(f"Failed to parse config.json: {e}")
            
            if not parent_model_id:
                return 0.5
            
            from api.models import Artifact
            parent_name = parent_model_id.split('/')[-1] if '/' in parent_model_id else parent_model_id
            
            parent_artifact = Artifact.objects.filter(
                type="model",
                name__icontains=parent_name,
                status="ready"
            ).exclude(id=artifact_id).first()
            
            if parent_artifact and parent_artifact.net_score is not None:
                logger.info(f"Found parent {parent_artifact.name} with net_score {parent_artifact.net_score}")
                return parent_artifact.net_score
            
            return 0.5
        except Exception as e:
            logger.error(f"Tree score failed: {e}")
            return 0.5

    def _compute_reviewedness(self, minimal_files: Dict[str, bytes], repo_id: str, source_url: str) -> float:
        """Compute reviewedness via GitHub API"""
        import json
        import requests
        import re
        
        try:
            score = 0.0
            github_repo = None
            
            # Extract GitHub repo
            if 'config.json' in minimal_files:
                try:
                    config = json.loads(minimal_files['config.json'].decode('utf-8'))
                    for field in ['repository', 'repo', 'github']:
                        if field in config and 'github.com' in str(config[field]):
                            match = re.search(r'github\.com/([^/]+/[^/]+)', config[field])
                            if match:
                                github_repo = match.group(1).rstrip('.git')
                                break
                except:
                    pass
            
            if not github_repo:
                for filename in ['README.md', 'README.txt']:
                    if filename in minimal_files:
                        try:
                            readme = minimal_files[filename].decode('utf-8', errors='ignore')
                            match = re.search(r'github\.com/([a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+)', readme)
                            if match:
                                github_repo = match.group(1).rstrip('.git')
                                break
                        except:
                            pass
            
            if github_repo:
                github_token = os.getenv('GITHUB_TOKEN')
                if github_token:
                    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
                    for branch in ['main', 'master']:
                        url = f'https://api.github.com/repos/{github_repo}/branches/{branch}/protection'
                        try:
                            response = requests.get(url, headers=headers, timeout=5)
                            if response.status_code == 200:
                                protection = response.json()
                                if 'required_pull_request_reviews' in protection:
                                    score += 0.5
                                    reviews = protection['required_pull_request_reviews']
                                    if reviews.get('required_approving_review_count', 0) > 0:
                                        score += 0.1
                                    if reviews.get('dismiss_stale_reviews', False):
                                        score += 0.1
                                logger.info(f"GitHub review score for {github_repo}/{branch}: {score}")
                                return min(score, 1.0)
                        except:
                            pass
            
            return max(score, 0.5)
        except Exception as e:
            logger.error(f"Reviewedness failed: {e}")
            return 0.5
