"""
S3 Zero-Disk Ingest Service

Wrapper service that uses S3ZeroDiskIngest for artifact ingestion.
This service integrates with Django models and provides the ingest_artifact interface.
"""
import os
import logging
from typing import Dict, Tuple, Optional
from django.db import transaction

from api.models import Artifact
from .s3_zero_disk_ingest import S3ZeroDiskIngest

logger = logging.getLogger(__name__)


class S3ZeroDiskIngestService:
    """
    Ingest service using zero-disk S3 streaming approach
    Everything happens in memory - no temp files on EC2
    """

    def __init__(self):
        self.zero_disk_ingest = S3ZeroDiskIngest()

    def ingest_artifact(
        self,
        source_url: str,
        artifact_type: str,
        revision: str = "main",
        uploaded_by=None
    ) -> Tuple[int, Dict]:
        """
        Ingest artifact from HuggingFace using zero-disk streaming

        Args:
            source_url: HuggingFace repo URL (e.g., https://huggingface.co/bert-base-uncased)
            artifact_type: One of 'model', 'dataset', 'code'
            revision: Git revision to download (default: 'main')
            uploaded_by: User who uploaded (optional)

        Returns:
            Tuple of (status_code, result_dict)
            - 201: Successfully created
            - 424: Failed dependency (rating too low)
            - 500: Internal server error
        """
        logger.info(f"Starting zero-disk ingest for {source_url} (type: {artifact_type})")

        # Parse repo_id from source_url
        repo_id = self._parse_repo_id(source_url)

        # Check for duplicates
        existing = Artifact.objects.filter(
            source_url=source_url,
            type=artifact_type
        ).first()
        if existing:
            logger.warning(f"Duplicate artifact: {source_url} already exists as ID {existing.id}")
            return 409, {
                "status": "error",
                "error": "Artifact exists already",
                "existing_id": existing.id
            }

        # Create artifact record
        with transaction.atomic():
            artifact = Artifact.objects.create(
                name=repo_id.split('/')[-1],
                source_url=source_url,
                type=artifact_type,
                status="downloading",
                uploaded_by=uploaded_by
            )
            artifact_id = artifact.id

        try:
            # Generate S3 key for the ZIP file
            s3_key = f"artifacts/{artifact_type}/{artifact_id}/{repo_id.replace('/', '_')}.zip"

            # Download and ZIP to S3 with zero disk usage
            sha256_hash, total_size = self.zero_disk_ingest.download_and_zip_to_s3_streaming(
                repo_id=repo_id,
                artifact_type=artifact_type,
                output_zip_key=s3_key,
                revision=revision,
                artifact_id=artifact_id
            )

            # Download minimal files for metrics (README, config)
            repo_type_map = {
                'model': 'model',
                'dataset': 'dataset',
                'code': 'space'
            }
            repo_type = repo_type_map.get(artifact_type, 'model')

            minimal_files = self.zero_disk_ingest.download_minimal_for_metrics(
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision
            )

            # Extract dataset/code names from README (for linking)
            dataset_name, code_name = self._extract_dependencies_from_readme(minimal_files)

            # Compute metrics using minimal files in memory
            with transaction.atomic():
                artifact.status = "rating"
                artifact.save()

            metrics = self._compute_metrics_from_memory(minimal_files, source_url, repo_id)

            # Calculate net score
            net_score = self._calculate_net_score(metrics)

            # Check if rating passes threshold (0.5)
            if net_score < 0.5:
                logger.warning(f"Artifact {artifact_id} rejected: net score {net_score} < 0.5")
                with transaction.atomic():
                    artifact.status = "rejected"
                    artifact.rating_scores = metrics
                    artifact.net_score = net_score
                    artifact.save()

                return 424, {
                    "id": artifact_id,
                    "status": "rejected",
                    "message": f"Package rating is too low: {net_score}",
                    "net_score": net_score,
                    "metrics": metrics
                }

            # Generate presigned download URL
            download_url = self.zero_disk_ingest.get_s3_presigned_url(s3_key, expiration=3600)

            # Update artifact with success
            with transaction.atomic():
                artifact.status = "completed"
                artifact.s3_key = s3_key
                artifact.download_url = download_url
                artifact.file_size = total_size
                artifact.sha256_hash = sha256_hash
                artifact.rating_scores = metrics
                artifact.net_score = net_score

                # Store dataset/code names and create relationships (for models only)
                if artifact_type == "model":
                    artifact.dataset_name = dataset_name
                    artifact.code_name = code_name

                    # Try to link to existing Dataset/Code records
                    if dataset_name:
                        from api.models import find_or_create_dataset
                        dataset = find_or_create_dataset(dataset_name)
                        artifact.dataset = dataset

                    if code_name:
                        from api.models import find_or_create_code
                        code = find_or_create_code(code_name)
                        artifact.code = code

                artifact.save()

            logger.info(f"Zero-disk ingest completed for artifact {artifact_id}")

            return 201, {
                "id": artifact_id,
                "status": "completed",
                "name": artifact.name,
                "net_score": net_score,
                "metrics": metrics,
                "download_url": download_url
            }

        except Exception as e:
            logger.error(f"Zero-disk ingest failed for artifact {artifact_id}: {e}")
            with transaction.atomic():
                artifact.status = "failed"
                artifact.save()

            return 500, {
                "error": str(e),
                "message": "Internal server error during ingest"
            }

    def _parse_repo_id(self, source_url: str) -> str:
        """Extract repo_id from HuggingFace URL"""
        # Example: https://huggingface.co/bert-base-uncased -> bert-base-uncased
        # Example: https://huggingface.co/datasets/squad -> squad
        url = source_url.rstrip('/')

        if 'huggingface.co/' in url:
            parts = url.split('huggingface.co/')[-1].split('/')
            # Remove 'datasets', 'spaces' prefix if present
            if parts[0] in ['datasets', 'spaces']:
                return '/'.join(parts[1:])
            return '/'.join(parts)

        return url

    def _extract_dependencies_from_readme(
        self,
        minimal_files: Dict[str, bytes]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract dataset and code names from README (in-memory)

        Args:
            minimal_files: Dict of {filename: bytes} containing README files

        Returns:
            Tuple of (dataset_name, code_name)
        """
        import re
        from typing import Optional

        # Get README content from memory
        readme_content = None
        for filename in ['README.md', 'README.txt', 'readme.md']:
            if filename in minimal_files:
                try:
                    readme_content = minimal_files[filename].decode('utf-8', errors='ignore')
                    break
                except Exception as e:
                    logger.warning(f"Failed to decode {filename}: {e}")
                    continue

        if not readme_content:
            return None, None

        try:
            # Extract dataset name
            dataset_pattern = r'(?:dataset|training[_\s]?data|trained[_\s]?on)[:\s]+([a-zA-Z0-9/_-]+)'
            dataset_match = re.search(dataset_pattern, readme_content, re.IGNORECASE)
            dataset_name = dataset_match.group(1) if dataset_match else None

            # Extract code name
            code_pattern = r'(?:code|repository|repo|github)[:\s]+([a-zA-Z0-9/_-]+)'
            code_match = re.search(code_pattern, readme_content, re.IGNORECASE)
            code_name = code_match.group(1) if code_match else None

            logger.info(f"Extracted dependencies - dataset: {dataset_name}, code: {code_name}")
            return dataset_name, code_name

        except Exception as e:
            logger.warning(f"Failed to extract dependencies: {e}")
            return None, None

    def _compute_metrics_from_memory(
        self,
        minimal_files: Dict[str, bytes],
        source_url: str,
        repo_id: str
    ) -> Dict:
        """
        Compute metrics using in-memory files (no disk usage)

        Args:
            minimal_files: Dict of {filename: bytes} for README, config, etc.
            source_url: HuggingFace URL
            repo_id: Repository ID

        Returns:
            Dict of metric scores
        """
        # Import metrics service
        try:
            import sys
            sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../src'))
            from Services.Metric_Model_Service import ModelMetricService

            metric_service = ModelMetricService()

            # Extract README content if available
            readme_content = None
            for filename in ['README.md', 'README.txt']:
                if filename in minimal_files:
                    readme_content = minimal_files[filename].decode('utf-8', errors='ignore')
                    break

            # Compute metrics
            metrics = {}

            # For now, use simple heuristics based on README
            # TODO: Integrate full metric service when available
            if readme_content:
                metrics['documentation'] = min(len(readme_content) / 1000, 1.0)  # Longer README = better
            else:
                metrics['documentation'] = 0.0

            # Default scores for other metrics
            metrics['ramp_up_time'] = 0.5
            metrics['bus_factor'] = 0.5
            metrics['correctness'] = 0.5
            metrics['responsive_maintainer'] = 0.5
            metrics['license_score'] = 0.5

            logger.info(f"Computed metrics for {repo_id}: {metrics}")
            return metrics

        except Exception as e:
            logger.error(f"Failed to compute metrics: {e}")
            # Return default metrics
            return {
                'documentation': 0.5,
                'ramp_up_time': 0.5,
                'bus_factor': 0.5,
                'correctness': 0.5,
                'responsive_maintainer': 0.5,
                'license_score': 0.5
            }

    def _calculate_net_score(self, metrics: Dict) -> float:
        """Calculate net score from metrics"""
        # Simple average for now
        # TODO: Use proper weighting formula
        values = [v for v in metrics.values() if isinstance(v, (int, float))]
        if not values:
            return 0.0
        return sum(values) / len(values)
