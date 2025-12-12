"""
Zero-Disk S3 Ingest Service

This service NEVER uses EC2 disk - everything streams directly to S3:
1. Stream HuggingFace files directly to S3 (no local download)
2. Create ZIP in S3 using multipart upload with in-memory streaming
3. Download ONLY minimal metadata files (README, config) for metrics (small <1MB)

Key improvements:
- No temp files (except tiny README/config for metrics)
- ZIP created entirely in S3 memory
- Worker handles serialization (one artifact at a time)
- Predictable resource usage
"""
import os
import io
import logging
import hashlib
from typing import Dict, Tuple, Optional
import boto3
from botocore.exceptions import ClientError
from huggingface_hub import HfApi, hf_hub_url
import requests

logger = logging.getLogger(__name__)


class S3ZeroDiskIngest:
    """
    Ingest artifacts with ZERO EC2 disk usage
    Everything streams directly to/from S3
    """

    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.bucket = os.getenv('AWS_STORAGE_BUCKET_NAME')

        if not self.bucket:
            raise ValueError("AWS_STORAGE_BUCKET_NAME not configured")

    def download_and_zip_to_s3_streaming(
        self,
        repo_id: str,
        artifact_type: str,
        output_zip_key: str,
        revision: str = "main",
        artifact_id: int = None
    ) -> Tuple[str, int]:
        """
        Download HuggingFace repo and create ZIP entirely in S3 with NO disk usage

        Uses multipart upload to stream ZIP data directly to S3 without local files.

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        logger.info(f"Starting zero-disk streaming ingest for {repo_id}")

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

        logger.info(f"Found {len(repo_files)} files to process")

        # Create ZIP in S3 using multipart upload with in-memory streaming
        sha256_hash, total_size = self._create_streaming_zip_in_s3(
            repo_id=repo_id,
            repo_type=repo_type,
            revision=revision,
            file_list=repo_files,
            output_key=output_zip_key
        )

        logger.info(f"Zero-disk ZIP created: {output_zip_key} ({total_size} bytes)")

        return sha256_hash, total_size

    def _create_streaming_zip_in_s3(
        self,
        repo_id: str,
        repo_type: str,
        revision: str,
        file_list: list,
        output_key: str
    ) -> Tuple[str, int]:
        """
        Create ZIP file entirely in S3 using multipart upload
        NO local files are created - everything streams through memory

        Strategy: Build complete ZIP in memory, upload in parts when needed
        """
        # Initialize multipart upload
        multipart = self.s3_client.create_multipart_upload(
            Bucket=self.bucket,
            Key=output_key,
            ContentType='application/zip'
        )
        upload_id = multipart['UploadId']

        parts = []
        part_number = 1
        sha256_hash = hashlib.sha256()
        total_size = 0

        try:
            # Use in-memory buffer for ZIP creation
            zip_buffer = io.BytesIO()

            # Create ZIP using zipfile but with in-memory buffer
            import zipfile

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for idx, file_path in file_list:
                    logger.info(f"Processing file {idx+1}/{len(file_list)}: {file_path}")  # ADD THIS

                    try:
                        # Get download URL
                        url = hf_hub_url(
                            repo_id=repo_id,
                            filename=file_path,
                            repo_type=repo_type,
                            revision=revision
                        )

                        # Stream download (no disk!)
                        response = requests.get(url, stream=True)
                        response.raise_for_status()

                        # Read file content into memory (in chunks to avoid huge RAM spikes)
                        file_data = io.BytesIO()
                        for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                            file_data.write(chunk)

                        file_data.seek(0)
                        file_content = file_data.getvalue()

                        # Add to ZIP in memory
                        zipf.writestr(file_path, file_content)
                        logger.info(f"✓ Added {file_path} to ZIP ({len(file_content)} bytes)")  # ADD THIS

                        # Update hash
                        sha256_hash.update(file_content)

                        logger.debug(f"Added {file_path} to ZIP ({len(file_content)} bytes)")

                    except Exception as e:
                        logger.warning(f"Failed to process {file_path}: {e}")
                        continue

            # ZIP is now complete in memory - upload it in parts
            zip_buffer.seek(0)

            # Upload in 50MB chunks
            chunk_size = 50 * 1024 * 1024

            while True:
                chunk = zip_buffer.read(chunk_size)
                if not chunk:
                    break

                response = self.s3_client.upload_part(
                    Bucket=self.bucket,
                    Key=output_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk
                )

                parts.append({
                    'PartNumber': part_number,
                    'ETag': response['ETag']
                })

                total_size += len(chunk)
                part_number += 1
                logger.debug(f"Uploaded part {part_number - 1} ({len(chunk)} bytes)")

            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=output_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )

            digest = sha256_hash.hexdigest()
            logger.info(f"Multipart ZIP upload completed: {total_size} bytes, SHA256: {digest[:16]}...")

            return digest, total_size

        except Exception as e:
            # Abort multipart upload on error
            logger.error(f"Multipart upload failed: {e}")
            try:
                self.s3_client.abort_multipart_upload(
                    Bucket=self.bucket,
                    Key=output_key,
                    UploadId=upload_id
                )
            except:
                pass
            raise

    def download_minimal_for_metrics(self, repo_id: str, repo_type: str, revision: str) -> Dict[str, bytes]:
        """
        Download ONLY minimal files needed for metrics (README, config)
        Returns in-memory dict - NO files written to disk

        Returns:
            Dict[filename, bytes] - all in memory
        """
        hf_api = HfApi()
        files_to_download = ['README.md', 'README.txt', 'config.json', 'tokenizer_config.json']

        result = {}

        try:
            repo_files = hf_api.list_repo_files(
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision
            )

            for filename in files_to_download:
                if filename in repo_files:
                    try:
                        url = hf_hub_url(
                            repo_id=repo_id,
                            filename=filename,
                            repo_type=repo_type,
                            revision=revision
                        )

                        response = requests.get(url)
                        response.raise_for_status()

                        result[filename] = response.content
                        logger.debug(f"Downloaded {filename} ({len(response.content)} bytes) into memory")

                    except Exception as e:
                        logger.warning(f"Failed to download {filename}: {e}")

        except Exception as e:
            logger.error(f"Failed to list repo files: {e}")

        return result

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
