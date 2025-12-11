"""
S3 Direct Ingest Service
Stream HuggingFace files directly to S3 to avoid EC2 RAM issues

This service:
1. Downloads files from HuggingFace directly to S3 (no EC2 disk/RAM)
2. Creates zip archive in S3 using multipart uploads
3. Processes metrics from S3 files
4. Stores in database only if metrics pass
"""
import os
import io
import zipfile
import hashlib
import logging
import tempfile
from typing import Dict, Tuple, Optional
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class S3DirectIngest:
    """
    Ingest artifacts directly to S3 without using EC2 disk/RAM
    """

    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.bucket = os.getenv('AWS_STORAGE_BUCKET_NAME')

        if not self.bucket:
            raise ValueError("AWS_STORAGE_BUCKET_NAME not configured")

    def download_hf_to_s3_direct(
        self,
        repo_id: str,
        artifact_type: str,
        revision: str = "main"
    ) -> Tuple[str, list]:
        """
        Download HuggingFace repo files directly to S3

        Returns:
            Tuple of (s3_folder_prefix, list_of_s3_keys)
        """
        from huggingface_hub import HfApi, hf_hub_url
        import requests

        hf_api = HfApi()

        # Determine repo type
        repo_type_map = {
            'model': 'model',
            'dataset': 'dataset',
            'code': 'space'
        }
        repo_type = repo_type_map.get(artifact_type, 'model')

        # Get list of files in repo
        try:
            repo_files = hf_api.list_repo_files(
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision
            )
        except Exception as e:
            logger.error(f"Failed to list HF repo files: {e}")
            raise

        # S3 folder for this artifact
        s3_prefix = f"tmp/hf_{artifact_type}/{repo_id.replace('/', '_')}/{revision}/"
        s3_keys = []

        logger.info(f"Streaming {len(repo_files)} files from HF to S3...")

        # Download each file directly to S3
        for file_path in repo_files:
            try:
                # Get download URL
                url = hf_hub_url(
                    repo_id=repo_id,
                    filename=file_path,
                    repo_type=repo_type,
                    revision=revision
                )

                # Stream download
                response = requests.get(url, stream=True)
                response.raise_for_status()

                # Upload to S3
                s3_key = f"{s3_prefix}{file_path}"

                # Use multipart upload for large files
                self.s3_client.upload_fileobj(
                    response.raw,
                    self.bucket,
                    s3_key
                )

                s3_keys.append(s3_key)
                logger.debug(f"Uploaded to S3: {s3_key}")

            except Exception as e:
                logger.warning(f"Failed to stream {file_path}: {e}")
                continue

        logger.info(f"Successfully streamed {len(s3_keys)} files to S3")
        return s3_prefix, s3_keys

    def create_zip_in_s3(self, s3_keys: list, output_key: str) -> Tuple[str, int]:
        """
        Create zip archive in S3 from existing S3 files
        Uses streaming to avoid loading everything into RAM

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        logger.info(f"Creating zip archive in S3: {output_key}")

        # Create temporary file for zip (small footprint)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
            tmp_zip_path = tmp_zip.name

        try:
            sha256_hash = hashlib.sha256()

            # Create zip file
            with zipfile.ZipFile(tmp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for s3_key in s3_keys:
                    try:
                        # Stream file from S3
                        response = self.s3_client.get_object(
                            Bucket=self.bucket,
                            Key=s3_key
                        )

                        # Get filename for zip archive
                        arcname = s3_key.split('/')[-1]

                        # Stream in chunks to avoid loading entire file into RAM
                        chunk_size = 1024 * 1024  # 1MB chunks
                        file_hash = hashlib.sha256()
                        
                        # Create a temporary file for this individual file
                        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                            tmp_file_path = tmp_file.name
                            
                            # Download in chunks
                            for chunk in iter(lambda: response['Body'].read(chunk_size), b''):
                                tmp_file.write(chunk)
                                file_hash.update(chunk)
                        
                        # Add the temp file to zip
                        zipf.write(tmp_file_path, arcname)
                        
                        # Update overall hash
                        sha256_hash.update(file_hash.digest())
                        
                        # Clean up temp file
                        os.remove(tmp_file_path)

                    except Exception as e:
                        logger.warning(f"Failed to add {s3_key} to zip: {e}")
                        continue

            # Upload zip to S3
            file_size = os.path.getsize(tmp_zip_path)

            with open(tmp_zip_path, 'rb') as f:
                self.s3_client.upload_fileobj(f, self.bucket, output_key)

            digest = sha256_hash.hexdigest()
            logger.info(f"Zip created: {output_key} ({file_size} bytes, SHA256: {digest[:16]}...)")

            return digest, file_size

        finally:
            # Cleanup temp file
            if os.path.exists(tmp_zip_path):
                os.remove(tmp_zip_path)

    def download_minimal_for_metrics(self, s3_keys: list) -> str:
        """
        Download only essential files (README, config) to temp dir for metrics
        Returns local temp directory path
        """
        temp_dir = tempfile.mkdtemp(prefix='metrics_')

        # Files needed for metrics
        essential_files = ['README.md', 'config.json', 'tokenizer_config.json']

        for s3_key in s3_keys:
            filename = s3_key.split('/')[-1]

            if filename in essential_files:
                try:
                    local_path = os.path.join(temp_dir, filename)
                    self.s3_client.download_file(self.bucket, s3_key, local_path)
                    logger.debug(f"Downloaded for metrics: {filename}")
                except Exception as e:
                    logger.warning(f"Failed to download {filename}: {e}")

        return temp_dir

    def cleanup_s3_temp_files(self, s3_prefix: str):
        """Delete temporary S3 files"""
        try:
            # List all objects with prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=s3_prefix
            )

            if 'Contents' not in response:
                return

            # Delete objects
            objects_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]

            if objects_to_delete:
                self.s3_client.delete_objects(
                    Bucket=self.bucket,
                    Delete={'Objects': objects_to_delete}
                )
                logger.info(f"Cleaned up {len(objects_to_delete)} temp files from S3")

        except Exception as e:
            logger.warning(f"Failed to cleanup S3 temp files: {e}")

    def get_s3_presigned_url(self, s3_key: str, expiration: int = 3600) -> str:
        """Generate presigned URL for downloading"""
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket, 'Key': s3_key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            return None
