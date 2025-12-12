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
        Create ZIP file with TRUE streaming - never holds full ZIP in memory

        Strategy:
        1. Stream files from HuggingFace one at a time
        2. Build ZIP format incrementally in memory buffer
        3. Upload to S3 multipart when buffer reaches threshold (10MB)
        4. Clear buffer and continue - constant memory usage
        """
        import zipfile
        import struct
        import time

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

        # Buffer for accumulating ZIP data before uploading
        # S3 multipart minimum is 5MB (except last part), we use 10MB for safety
        upload_buffer = io.BytesIO()
        min_part_size = 10 * 1024 * 1024  # 10MB

        # ZIP central directory - built as we go
        central_directory = []
        offset = 0  # Track offset in final ZIP file

        try:
            for file_path in file_list:
                try:
                    # Get download URL
                    url = hf_hub_url(
                        repo_id=repo_id,
                        filename=file_path,
                        repo_type=repo_type,
                        revision=revision
                    )

                    # Stream download from HuggingFace
                    response = requests.get(url, stream=True)
                    response.raise_for_status()

                    # Get file size if available
                    file_size = int(response.headers.get('content-length', 0))

                    # Build ZIP local file header
                    filename_bytes = file_path.encode('utf-8')
                    local_header_offset = offset

                    # ZIP local file header (simplified - no compression for streaming)
                    local_header = struct.pack('<I', 0x04034b50)  # Local file header signature
                    local_header += struct.pack('<H', 10)  # Version needed
                    local_header += struct.pack('<H', 0)   # Flags
                    local_header += struct.pack('<H', 0)   # Compression (0=stored, no compression)
                    local_header += struct.pack('<H', 0)   # Mod time
                    local_header += struct.pack('<H', 0)   # Mod date
                    local_header += struct.pack('<I', 0)   # CRC32 (will update later)
                    local_header += struct.pack('<I', file_size)  # Compressed size
                    local_header += struct.pack('<I', file_size)  # Uncompressed size
                    local_header += struct.pack('<H', len(filename_bytes))  # Filename length
                    local_header += struct.pack('<H', 0)   # Extra field length
                    local_header += filename_bytes

                    upload_buffer.write(local_header)
                    offset += len(local_header)
                    sha256_hash.update(local_header)

                    # Stream file content and calculate CRC32
                    import zlib
                    crc32 = 0
                    actual_size = 0

                    for chunk in response.iter_content(chunk_size=1024 * 1024):  # 1MB chunks
                        if chunk:
                            upload_buffer.write(chunk)
                            offset += len(chunk)
                            actual_size += len(chunk)
                            crc32 = zlib.crc32(chunk, crc32)
                            sha256_hash.update(chunk)

                            # Upload when buffer reaches threshold
                            if upload_buffer.tell() >= min_part_size:
                                upload_buffer.seek(0)
                                chunk_data = upload_buffer.read()

                                response_part = self.s3_client.upload_part(
                                    Bucket=self.bucket,
                                    Key=output_key,
                                    PartNumber=part_number,
                                    UploadId=upload_id,
                                    Body=chunk_data
                                )

                                parts.append({
                                    'PartNumber': part_number,
                                    'ETag': response_part['ETag']
                                })

                                total_size += len(chunk_data)
                                part_number += 1
                                logger.debug(f"Uploaded part {part_number - 1} ({len(chunk_data)} bytes)")

                                # Clear buffer for next part
                                upload_buffer = io.BytesIO()

                    # Store central directory entry
                    central_directory.append({
                        'filename': filename_bytes,
                        'crc32': crc32 & 0xffffffff,
                        'size': actual_size,
                        'offset': local_header_offset
                    })

                    logger.debug(f"Added {file_path} to ZIP ({actual_size} bytes)")

                except Exception as e:
                    logger.warning(f"Failed to process {file_path}: {e}")
                    continue

            # Build central directory
            central_dir_start = offset
            central_dir_data = io.BytesIO()

            for entry in central_directory:
                cd_header = struct.pack('<I', 0x02014b50)  # Central directory signature
                cd_header += struct.pack('<H', 10)  # Version made by
                cd_header += struct.pack('<H', 10)  # Version needed
                cd_header += struct.pack('<H', 0)   # Flags
                cd_header += struct.pack('<H', 0)   # Compression
                cd_header += struct.pack('<H', 0)   # Mod time
                cd_header += struct.pack('<H', 0)   # Mod date
                cd_header += struct.pack('<I', entry['crc32'])
                cd_header += struct.pack('<I', entry['size'])  # Compressed
                cd_header += struct.pack('<I', entry['size'])  # Uncompressed
                cd_header += struct.pack('<H', len(entry['filename']))
                cd_header += struct.pack('<H', 0)   # Extra field length
                cd_header += struct.pack('<H', 0)   # Comment length
                cd_header += struct.pack('<H', 0)   # Disk number
                cd_header += struct.pack('<H', 0)   # Internal attributes
                cd_header += struct.pack('<I', 0)   # External attributes
                cd_header += struct.pack('<I', entry['offset'])
                cd_header += entry['filename']

                central_dir_data.write(cd_header)
                offset += len(cd_header)

            central_dir_bytes = central_dir_data.getvalue()
            upload_buffer.write(central_dir_bytes)
            sha256_hash.update(central_dir_bytes)

            # End of central directory record
            eocd = struct.pack('<I', 0x06054b50)  # EOCD signature
            eocd += struct.pack('<H', 0)   # Disk number
            eocd += struct.pack('<H', 0)   # Disk with central dir
            eocd += struct.pack('<H', len(central_directory))  # Entries on this disk
            eocd += struct.pack('<H', len(central_directory))  # Total entries
            eocd += struct.pack('<I', len(central_dir_bytes))  # Central dir size
            eocd += struct.pack('<I', central_dir_start)  # Central dir offset
            eocd += struct.pack('<H', 0)   # Comment length

            upload_buffer.write(eocd)
            sha256_hash.update(eocd)
            offset += len(eocd)

            # Upload final buffer
            if upload_buffer.tell() > 0:
                upload_buffer.seek(0)
                final_data = upload_buffer.read()

                response_part = self.s3_client.upload_part(
                    Bucket=self.bucket,
                    Key=output_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=final_data
                )

                parts.append({
                    'PartNumber': part_number,
                    'ETag': response_part['ETag']
                })

                total_size += len(final_data)
                logger.debug(f"Uploaded final part {part_number} ({len(final_data)} bytes)")

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
        Download minimal files + metadata needed for ALL metrics calculation
        Returns in-memory dict - NO files written to disk

        Downloads:
        - Files: README, config, tokenizer_config
        - HuggingFace API metadata: repo info, commits, size
        - File list for code quality analysis

        Returns:
            Dict with file contents + metadata - all in memory
        """
        hf_api = HfApi()
        files_to_download = ['README.md', 'README.txt', 'config.json', 'tokenizer_config.json']

        result = {}

        try:
            # 1. Download text files
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

            # 2. Fetch repo metadata (for size, license, bus factor)
            try:
                import json
                repo_info = hf_api.repo_info(
                    repo_id=repo_id,
                    repo_type=repo_type,
                    revision=revision
                )

                # Extract relevant metadata
                metadata = {
                    'size_mb': getattr(repo_info, 'size_bytes', 0) / (1024 * 1024) if hasattr(repo_info, 'size_bytes') else 0,
                    'license': getattr(repo_info, 'cardData', {}).get('license') if hasattr(repo_info, 'cardData') else None,
                    'last_modified': str(getattr(repo_info, 'lastModified', None)),
                    'downloads': getattr(repo_info, 'downloads', 0),
                    'likes': getattr(repo_info, 'likes', 0),
                }
                result['_hf_repo_metadata'] = json.dumps(metadata).encode('utf-8')
                logger.debug(f"Fetched HF repo metadata: {metadata}")
            except Exception as e:
                logger.warning(f"Failed to fetch repo metadata: {e}")

            # 3. Fetch commit history (for bus factor)
            try:
                import json
                commits = list(hf_api.list_repo_commits(
                    repo_id=repo_id,
                    repo_type=repo_type,
                    revision=revision
                ))[:50]  # Last 50 commits

                commit_data = []
                unique_authors = set()
                for commit in commits:
                    commit_info = {
                        'commit_id': commit.commit_id,
                        'date': str(commit.created_at),
                        'author': commit.author if hasattr(commit, 'author') else 'unknown',
                        'title': commit.title if hasattr(commit, 'title') else ''
                    }
                    commit_data.append(commit_info)
                    if hasattr(commit, 'author') and commit.author:
                        unique_authors.add(commit.author)

                result['_hf_commit_history'] = json.dumps(commit_data).encode('utf-8')
                result['_hf_contributors_count'] = json.dumps({'count': len(unique_authors)}).encode('utf-8')
                logger.debug(f"Fetched {len(commit_data)} commits, {len(unique_authors)} unique contributors")
            except Exception as e:
                logger.warning(f"Failed to fetch commit history: {e}")

            # 4. Get file list structure (for code quality)
            try:
                import json
                # Store file list with types (file/directory)
                file_structure = []
                for filepath in repo_files[:200]:  # Limit to first 200 files
                    file_structure.append({
                        'name': filepath.split('/')[-1],
                        'path': filepath,
                        'type': 'file'  # HF API doesn't distinguish, assume file
                    })
                result['_hf_file_structure'] = json.dumps(file_structure).encode('utf-8')
                logger.debug(f"Stored file structure: {len(file_structure)} files")
            except Exception as e:
                logger.warning(f"Failed to store file structure: {e}")

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
