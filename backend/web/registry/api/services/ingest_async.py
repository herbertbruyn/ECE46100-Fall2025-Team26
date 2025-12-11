"""
Async Ingest Service with 202 Response Pattern

This service handles the EC2 portion of artifact ingestion:
- Validates request (400, 403, 409 errors)
- Creates artifact record with status="pending"
- Triggers Lambda for async processing
- Returns 202 Accepted immediately

The Lambda function handles the heavy processing (download, zip, rate)
and updates the database when complete or failed.
"""
import os
import logging
import json
import boto3
from typing import Dict, Tuple
from django.db import transaction

from api.models import Artifact

logger = logging.getLogger(__name__)


class AsyncIngestService:
    """
    Fast ingest service that returns 202 and delegates to Lambda
    """

    def __init__(self):
        region = os.getenv('AWS_REGION') or os.getenv('AWS_DEFAULT_REGION', 'us-east-2')
        self.lambda_client = boto3.client('lambda', region_name=region)
        self.lambda_function = os.getenv('INGEST_LAMBDA_FUNCTION', 'artifact-ingest-processor')

    def ingest_artifact(
        self,
        source_url: str,
        artifact_type: str,
        revision: str = "main",
        uploaded_by=None
    ) -> Tuple[int, Dict]:
        """
        Synchronous validation + async processing

        Returns:
            (202, {...}) on success - artifact queued for processing
            (400, {...}) on validation error
            (409, {...}) if duplicate exists
            (500, {...}) on server error
        """
        try:
            # Step 1: Extract and validate
            repo_id = self._extract_repo_id(source_url)
            name = repo_id.split('/')[-1]

            # Step 2: Check for duplicates (409)
            existing = Artifact.objects.filter(
                source_url=source_url,
                type=artifact_type
            ).first()

            if existing:
                # If already completed, return 409
                if existing.status == "completed":
                    return 409, {
                        "detail": "Artifact exists already.",
                        "existing_id": existing.id,
                        "status": existing.status
                    }

                # If currently processing, also return 409
                if existing.status in ["pending", "downloading", "rating"]:
                    return 409, {
                        "detail": "Artifact is already being processed.",
                        "existing_id": existing.id,
                        "status": existing.status
                    }

                # If previously failed or rejected, allow retry by deleting old record
                logger.info(f"Retrying previously {existing.status} artifact {existing.id}")
                existing.delete()

            # Step 3: Create artifact with "pending" status
            with transaction.atomic():
                artifact = Artifact.objects.create(
                    name=name,
                    type=artifact_type,
                    source_url=source_url,
                    status="pending",
                    uploaded_by=uploaded_by
                )
                logger.info(f"Created artifact {artifact.id} with status=pending")

            # Step 4: Trigger Lambda asynchronously
            self._invoke_lambda_async(
                artifact_id=artifact.id,
                source_url=source_url,
                artifact_type=artifact_type,
                revision=revision,
                name=name
            )

            # Step 5: Return 202 Accepted immediately
            return 202, {
                "message": "Artifact ingest accepted. Processing asynchronously.",
                "artifact_id": artifact.id,
                "status": "pending",
                "note": "Use GET /artifacts/{type}/{id} to check processing status. Artifact will be available when status='completed'."
            }

        except ValueError as e:
            # Invalid URL format
            return 400, {
                "detail": f"Invalid artifact URL: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Ingest failed: {str(e)}", exc_info=True)
            return 500, {
                "detail": f"Server error: {str(e)}"
            }

    def _extract_repo_id(self, url: str) -> str:
        """Extract repo ID from Hugging Face URL"""
        url = url.rstrip('/')

        if '/datasets/' in url:
            repo_id = url.split('/datasets/')[-1]
        elif '/spaces/' in url:
            repo_id = url.split('/spaces/')[-1]
        elif 'huggingface.co/' in url:
            parts = url.split('huggingface.co/')
            if len(parts) > 1:
                repo_id = parts[-1]
            else:
                raise ValueError(f"Invalid Hugging Face URL: {url}")
        else:
            raise ValueError(f"Invalid Hugging Face URL: {url}")

        # Remove any trailing path components (like /tree/main)
        if '/tree/' in repo_id:
            repo_id = repo_id.split('/tree/')[0]

        return repo_id

    def _invoke_lambda_async(
        self,
        artifact_id: int,
        source_url: str,
        artifact_type: str,
        revision: str,
        name: str
    ):
        """
        Invoke Lambda function asynchronously

        Lambda will:
        1. Download files to S3
        2. Create zip
        3. Compute ratings
        4. Update database (status=completed or rejected)
        """
        try:
            payload = {
                'artifact_id': artifact_id,
                'source_url': source_url,
                'artifact_type': artifact_type,
                'revision': revision,
                'name': name
            }

            response = self.lambda_client.invoke(
                FunctionName=self.lambda_function,
                InvocationType='Event',  # Async invocation
                Payload=json.dumps(payload)
            )

            logger.info(
                f"Lambda invoked for artifact {artifact_id}: "
                f"StatusCode={response['StatusCode']}"
            )

        except Exception as e:
            logger.error(f"Failed to invoke Lambda: {str(e)}", exc_info=True)
            # Update artifact status to failed
            try:
                artifact = Artifact.objects.get(id=artifact_id)
                artifact.status = "failed"
                artifact.status_message = f"Failed to trigger processing: {str(e)}"
                artifact.save()
            except:
                pass
            raise
