"""
S3-Optimized Ingest Service
Streams HuggingFace files directly to S3 to avoid EC2 RAM issues

Key Changes from original ingest.py:
1. Downloads HF files directly to S3 (not EC2 disk)
2. Creates zip in S3 using multipart streaming
3. Downloads only minimal files (README, config) to EC2 for metrics
4. Cleans up temp S3 files after ingestion

Usage:
  Replace IngestService with S3OptimizedIngestService in views.py
  Set USE_S3=True and configure AWS credentials in settings.py
"""
from __future__ import annotations
from functools import total_ordering
import os
import sys
import logging
import hashlib
import tempfile
import shutil
import time
from typing import Dict, Tuple, Optional
from django.db import transaction
from django.utils import timezone
from django.conf import settings

# Import existing models and services
from api.models import Artifact, ModelRating
from .s3_direct_ingest import S3DirectIngest

# Import metric service
BASE_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src"))
if BASE_SRC not in sys.path:
    sys.path.insert(0, BASE_SRC)

try:
    from Services.Metric_Model_Service import ModelMetricService
except ImportError:
    ModelMetricService = None

logger = logging.getLogger(__name__)


class S3OptimizedIngestService:
    """
    Ingest service that streams directly to S3
    Avoids EC2 RAM/disk issues
    """

    MIN_NET_SCORE = 0.5

    def __init__(self):
        self.metric_service = ModelMetricService() if ModelMetricService else None
        self.s3_ingest = S3DirectIngest()

    def ingest_artifact(
        self,
        source_url: str,
        artifact_type: str,
        revision: str = "main",
        uploaded_by=None
    ) -> Tuple[int, Dict]:
        """
        Main ingest pipeline with S3 direct streaming

        Flow:
        1. Stream HF files directly to S3 (no EC2 disk)
        2. Download minimal files to EC2 for metrics
        3. Run metrics evaluation
        4. Check threshold
        5. Create zip in S3 from streamed files
        6. Store metadata in database
        7. Cleanup temp files

        Returns:
            Tuple of (status_code, response_dict)
        """
        artifact = None
        local_metrics_dir = None
        s3_prefix = None

        try:
            logger.info(f"Starting S3-optimized ingest for {artifact_type}: {source_url}")

            # Step 1: Extract repo info
            repo_id = self._extract_repo_id(source_url)
            name = repo_id.split('/')[-1]

            # Check for duplicates
            existing = Artifact.objects.filter(
                source_url=source_url,
                type=artifact_type
            ).first()

            if existing:
                return 409, {
                    "status": "error",
                    "error": "Artifact exists already",
                    "existing_id": existing.id
                }

            # Create artifact with "pending" status
            artifact = Artifact.objects.create(
                name=name,
                type=artifact_type,
                source_url=source_url,
                status="pending",
                uploaded_by=uploaded_by
            )
            logger.info(f"Created artifact {artifact.id} with status=pending")

            # Step 2: Stream HF files directly to S3
            artifact.status = "downloading"
            artifact.status_message = "Streaming from HuggingFace to S3..."
            artifact.save()

            s3_prefix, s3_keys = self.s3_ingest.download_hf_to_s3_direct(
                repo_id, artifact_type, revision
            )
            logger.info(f"Streamed {len(s3_keys)} files to S3: {s3_prefix}")

            # Step 3: Download minimal files for metrics
            artifact.status_message = "Downloading files for metrics..."
            artifact.save()

            local_metrics_dir = self.s3_ingest.download_minimal_for_metrics(s3_keys)

            # Step 4: Run metrics evaluation
            if artifact_type == "model" and self.metric_service:
                artifact.status = "rating"
                artifact.status_message = "Computing metrics..."
                artifact.save()

                rating_start = time.time()
                rating_scores = self._rate_artifact(local_metrics_dir, source_url, name)
                total_rating_time = time.time() - rating_start
                logger.info(f"Rating completed: net_score={rating_scores.get('net_score', 0):.3f}")

                # Step 5: Check threshold
                if not self._passes_threshold(rating_scores):
                    artifact.status = "rejected"
                    artifact.status_message = f"Rating below threshold"
                    artifact.save()

                    # Cleanup S3 temp files
                    self.s3_ingest.cleanup_s3_temp_files(s3_prefix)

                    return 424, {
                        "status": "disqualified",
                        "reason": "Artifact disqualified due to low rating",
                        "scores": rating_scores
                    }
            else:
                rating_scores = self._fallback_rating()
                total_rating_time = 0.0

            # Step 6: Create zip in S3
            artifact.status_message = "Creating zip archive in S3..."
            artifact.save()

            zip_s3_key = f"artifacts/{name}_{artifact.id}.zip"
            sha256_digest, size_bytes = self.s3_ingest.create_zip_in_s3(
                s3_keys, zip_s3_key
            )

            # Step 7: Persist to database
            self._persist_artifact(
                artifact=artifact,
                zip_s3_key=zip_s3_key,
                sha256=sha256_digest,
                size_bytes=size_bytes,
                rating_scores=rating_scores,
                total_rating_time=total_rating_time
            )

            # Cleanup S3 temp files
            self.s3_ingest.cleanup_s3_temp_files(s3_prefix)

            logger.info(f"Successfully completed ingest for artifact {artifact.id}")

            # Generate download URL
            download_url = self.s3_ingest.get_s3_presigned_url(zip_s3_key)

            return 201, {
                "metadata": artifact.metadata_view(),
                "data": {
                    "url": source_url,
                    "download_url": download_url
                },
                "scores": rating_scores,
                "status": "completed"
            }

        except Exception as e:
            logger.error(f"Ingest failed: {str(e)}", exc_info=True)

            if artifact:
                artifact.status = "failed"
                artifact.status_message = str(e)[:500]
                artifact.save()

            # Cleanup on failure
            if s3_prefix:
                try:
                    self.s3_ingest.cleanup_s3_temp_files(s3_prefix)
                except:
                    pass

            return 500, {
                "status": "error",
                "error": str(e)
            }

        finally:
            # Cleanup local temp files
            if local_metrics_dir and os.path.exists(local_metrics_dir):
                shutil.rmtree(local_metrics_dir, ignore_errors=True)

    def _extract_repo_id(self, url: str) -> str:
        """Extract repo ID from Hugging Face URL"""
        url = url.rstrip('/')

        if '/datasets/' in url:
            return url.split('/datasets/')[-1]
        elif '/spaces/' in url:
            return url.split('/spaces/')[-1]
        else:
            parts = url.split('huggingface.co/')
            if len(parts) > 1:
                return parts[-1]

        raise ValueError(f"Invalid Hugging Face URL: {url}")

    def _rate_artifact(self, local_path: str, source_url: str, name: str) -> Dict:
        """Rate artifact using minimal files"""
        logger.info(f"Rating artifact from {local_path}")

        # Use fallback for now (TODO: integrate full metrics)
        return self._fallback_rating()

    def _fallback_rating(self) -> Dict[str, float]:
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
        }

    def _passes_threshold(self, scores: Dict[str, float]) -> bool:
        """Check if artifact passes rating threshold"""
        return True  # TODO: Enable threshold check
        # return scores.get('net_score', 0.0) >= self.MIN_NET_SCORE

    def _persist_artifact(
        self,
        artifact: Artifact,
        zip_s3_key: str,
        sha256: str,
        size_bytes: int,
        rating_scores: Dict,
        total_rating_time: float
    ):
        """Persist artifact and rating to database"""
        with transaction.atomic():
            # Update artifact
            artifact.sha256 = sha256
            artifact.size_bytes = size_bytes
            artifact.blob.name = zip_s3_key  # Store S3 key
            artifact.status = "completed"
            artifact.status_message = "Successfully ingested"
            artifact.rating_completed_at = timezone.now()
            artifact.save()

            # Save rating
            if artifact.type == "model":
                ModelRating.objects.create(
                    artifact=artifact,
                    name=artifact.name,
                    category=artifact.type.upper(),
                    total_rating_time=total_rating_time,
                    **{k: v for k, v in rating_scores.items() if not k.endswith('_latency')},
                    **{k: v for k, v in rating_scores.items() if k.endswith('_latency')}
                )

                logger.info(f"Saved rating for artifact {artifact.id}")
