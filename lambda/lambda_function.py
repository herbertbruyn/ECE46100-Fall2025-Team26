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
from typing import Dict

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

            # Compute ratings (using fallback for now)
            rating_scores = compute_ratings(local_metrics_dir, source_url, name)
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


def compute_ratings(local_path: str, source_url: str, name: str) -> Dict:
    """
    Compute ratings for the artifact

    TODO: Integrate actual metric computation
    For now, using fallback values
    """
    return fallback_rating()


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
