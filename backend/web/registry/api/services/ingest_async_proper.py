"""
Async Ingest Service - Returns 202 and queues background work

Implements the spec's async flow:
1. POST returns 202 with artifact ID
2. Background worker does rating + ingest
3. GET returns 404 until status=ready
"""
import os
import logging
import json
from typing import Dict, Tuple, Optional
from django.db import transaction
import boto3

from api.models import Artifact

logger = logging.getLogger(__name__)


class AsyncIngestService:
    """
    Async ingest service - returns 202 immediately, queues work for background
    """

    def __init__(self):
        # Initialize SQS client for job queue
        self.sqs_client = None
        self.queue_url = os.getenv('SQS_QUEUE_URL')

        if self.queue_url:
            try:
                self.sqs_client = boto3.client('sqs')
                logger.info(f"Initialized SQS client with queue: {self.queue_url}")
            except Exception as e:
                logger.error(f"Failed to initialize SQS client: {e}")

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
        logger.info(f"Async ingest request for {source_url} (type: {artifact_type})")

        # Validate artifact_type
        valid_types = ['model', 'dataset', 'code']
        if artifact_type not in valid_types:
            return 400, {
                "error": f"Invalid artifact_type. Must be one of: {', '.join(valid_types)}"
            }

        # Parse repo_id from source_url
        repo_id = self._parse_repo_id(source_url)
        if not repo_id:
            return 400, {
                "error": "Invalid HuggingFace URL"
            }

        # Check for duplicates (only READY artifacts count as duplicates)
        existing = Artifact.objects.filter(
            source_url=source_url,
            type=artifact_type,
            status="ready"
        ).first()

        if existing:
            logger.warning(f"Duplicate artifact: {source_url} already exists as ID {existing.id}")
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
                logger.info(f"Queued artifact {artifact_id} for async processing")
            except Exception as e:
                logger.error(f"Failed to queue job: {e}")
                # Mark as failed if we can't queue
                with transaction.atomic():
                    artifact.status = "failed"
                    artifact.save()
                return 500, {
                    "error": "Failed to queue artifact for processing"
                }
        else:
            # Fallback: use threading for local development
            logger.warning("SQS not configured, using thread for async processing")
            import threading
            thread = threading.Thread(
                target=self._process_artifact_background,
                args=(job_data,)
            )
            thread.daemon = True
            thread.start()

        # Return 202 Accepted with artifact metadata
        # Per spec: download_url is not yet available
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

            # STEP 1: Rating
            artifact.status = "rating_in_progress"
            artifact.save()

            zero_disk = S3ZeroDiskIngest()

            # Download minimal files for rating
            repo_id = self._parse_repo_id(source_url)
            repo_type_map = {'model': 'model', 'dataset': 'dataset', 'code': 'space'}
            repo_type = repo_type_map.get(artifact_type, 'model')

            minimal_files = zero_disk.download_minimal_for_metrics(
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision
            )

            # Compute metrics
            metrics = self._compute_metrics(minimal_files, source_url, repo_id)
            net_score = self._calculate_net_score(metrics)

            # STEP 2: Quality gate check
            if net_score < 0.5:
                logger.warning(f"Artifact {artifact_id} disqualified: score {net_score} < 0.5")
                with transaction.atomic():
                    artifact.status = "disqualified"
                    artifact.rating_scores = metrics
                    artifact.net_score = net_score
                    artifact.save()
                return  # Don't ingest, artifact stays hidden (404)

            # STEP 3: Ingest artifact to S3
            artifact.status = "ingesting"
            artifact.save()

            s3_key = f"artifacts/{artifact_type}/{artifact_id}/{repo_id.replace('/', '_')}.zip"
            sha256_hash, total_size = zero_disk.download_and_zip_to_s3_streaming(
                repo_id=repo_id,
                artifact_type=artifact_type,
                output_zip_key=s3_key,
                revision=revision,
                artifact_id=artifact_id
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
                if artifact_type == "model":
                    dataset_name, code_name = self._extract_dependencies(minimal_files)
                    if dataset_name or code_name:
                        from api.models import find_or_create_dataset, find_or_create_code
                        if dataset_name:
                            artifact.dataset_name = dataset_name
                            artifact.dataset = find_or_create_dataset(dataset_name)
                        if code_name:
                            artifact.code_name = code_name
                            artifact.code = find_or_create_code(code_name)

                artifact.save()

            logger.info(f"Artifact {artifact_id} ready!")

        except Exception as e:
            logger.error(f"Background processing failed for artifact {artifact_id}: {e}")
            try:
                artifact = Artifact.objects.get(id=artifact_id)
                artifact.status = "failed"
                artifact.save()
            except:
                pass

    def _parse_repo_id(self, source_url: str) -> Optional[str]:
        """Extract repo_id from HuggingFace URL"""
        url = source_url.rstrip('/')
        if 'huggingface.co/' in url:
            parts = url.split('huggingface.co/')[-1].split('/')
            if parts[0] in ['datasets', 'spaces']:
                return '/'.join(parts[1:])
            return '/'.join(parts)
        return None

    def _compute_metrics(self, minimal_files: Dict[str, bytes], source_url: str, repo_id: str) -> Dict:
        """Compute metrics (simplified for now)"""
        # TODO: Integrate full ModelMetricService
        readme_content = None
        for filename in ['README.md', 'README.txt']:
            if filename in minimal_files:
                try:
                    readme_content = minimal_files[filename].decode('utf-8', errors='ignore')
                    break
                except:
                    pass

        metrics = {
            'documentation': min(len(readme_content) / 1000, 1.0) if readme_content else 0.0,
            'ramp_up_time': 0.5,
            'bus_factor': 0.5,
            'correctness': 0.5,
            'responsive_maintainer': 0.5,
            'license_score': 0.5
        }
        return metrics

    def _calculate_net_score(self, metrics: Dict) -> float:
        """Calculate net score"""
        values = [v for v in metrics.values() if isinstance(v, (int, float))]
        return sum(values) / len(values) if values else 0.0

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
