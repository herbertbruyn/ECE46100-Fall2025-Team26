#!/usr/bin/env python
"""
Background Worker for Async Artifact Ingestion

Polls SQS queue (or uses threading fallback) to process artifacts:
1. Rate the artifact
2. If quality gate passes, ingest to S3
3. Mark as ready or disqualified

Run this alongside Django:
    python worker.py
"""
import os
import sys
import django
import time
import json
import logging

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'registry.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from api.services.ingest_async_proper import AsyncIngestService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def process_sqs_messages(service: AsyncIngestService):
    """Process messages from SQS queue"""
    import boto3
    from botocore.exceptions import ClientError

    queue_url = os.getenv('SQS_QUEUE_URL')
    if not queue_url:
        logger.error("SQS_QUEUE_URL not set")
        return

    sqs_client = boto3.client('sqs', region_name=os.getenv('AWS_REGION'))
    logger.info(f"Starting SQS worker, polling: {queue_url}")

    while True:
        try:
            # Poll for messages
            response = sqs_client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,  # Long polling
                VisibilityTimeout=1800  # 10 minutes to process
            )

            messages = response.get('Messages', [])
            if not messages:
                continue

            for message in messages:
                try:
                    # Parse message
                    job_data = json.loads(message['Body'])
                    logger.info(f"Processing artifact {job_data.get('artifact_id')}")

                    # Process in background
                    service._process_artifact_background(job_data)

                    # Delete message from queue
                    sqs_client.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=message['ReceiptHandle']
                    )

                    logger.info(f"Completed artifact {job_data.get('artifact_id')}")

                except Exception as e:
                    logger.error(f"Failed to process message: {e}")
                    # Message will become visible again after VisibilityTimeout

        except ClientError as e:
            logger.error(f"SQS error: {e}")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(5)


def process_local_queue(service: AsyncIngestService):
    """
    Fallback: Process using database polling (for local dev without SQS)
    """
    from api.models import Artifact

    logger.info("Starting local queue worker (polling database)")

    while True:
        try:
            # Find pending artifacts
            pending = Artifact.objects.filter(
                status="pending_rating"
            ).order_by('created_at')[:1]

            if pending:
                artifact = pending[0]
                logger.info(f"Processing artifact {artifact.id}")

                job_data = {
                    'artifact_id': artifact.id,
                    'artifact_type': artifact.type,
                    'source_url': artifact.source_url,
                    'revision': 'main',
                    'uploaded_by_id': artifact.uploaded_by.id if artifact.uploaded_by else None
                }

                try:
                    service._process_artifact_background(job_data)
                    logger.info(f"Completed artifact {artifact.id}")
                except Exception as e:
                    logger.error(f"Failed to process artifact {artifact.id}: {e}")
                    # Mark as failed and continue
                    try:
                        artifact.status = "failed"
                        artifact.save()
                    except:
                        pass

            time.sleep(5)  # Poll every 5 seconds

        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            break
        except Exception as e:
            logger.error(f"Worker error: {e}")
            time.sleep(10)


def main():
    """Main worker entry point"""
    try:
        service = AsyncIngestService()

        # Check if SQS is configured
        if os.getenv('SQS_QUEUE_URL'):
            logger.info("Using SQS queue")
            try:
                process_sqs_messages(service)
            except Exception as e:
                logger.error(f"SQS worker failed, falling back to local queue: {e}")
                # Fallback to local queue if SQS fails
                process_local_queue(service)
        else:
            logger.info("SQS not configured, using local database polling")
            process_local_queue(service)
    except Exception as e:
        logger.error(f"Worker failed to start: {e}")
        # Sleep to prevent rapid restart loops
        time.sleep(60)


if __name__ == '__main__':
    main()
