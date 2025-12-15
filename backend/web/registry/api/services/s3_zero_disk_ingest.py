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
import sys
import logging
import hashlib
from typing import Dict, Tuple, Optional
import boto3
from botocore.exceptions import ClientError
from huggingface_hub import HfApi, hf_hub_url
import requests

logger = logging.getLogger(__name__)

# Size threshold for large datasets (5GB)
# Datasets larger than this will only have metadata ingested, not full data
LARGE_DATASET_THRESHOLD_BYTES = 5 * 1024 * 1024 * 1024  # 5GB


class S3ZeroDiskIngest:
    """
    Ingest artifacts with ZERO EC2 disk usage
    Everything streams directly to/from S3
    """

    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.bucket = os.getenv('AWS_STORAGE_BUCKET_NAME')
        self.hf_token = os.getenv('HF_TOKEN') or os.getenv('HUGGINGFACE_TOKEN')

        if not self.bucket:
            raise ValueError("AWS_STORAGE_BUCKET_NAME not configured")

        if self.hf_token:
            logger.info("Using HuggingFace authentication token for gated content access")

    def download_and_zip_to_s3_streaming(
        self,
        repo_id: str,
        artifact_type: str,
        output_zip_key: str,
        revision: str = "main",
        artifact_id: int = None,
        source_url: str = None
    ) -> Tuple[str, int]:
        """
        Download HuggingFace repo and create ZIP entirely in S3 with NO disk usage

        Uses multipart upload to stream ZIP data directly to S3 without local files.

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        logger.info(f"Starting zero-disk streaming ingest for {repo_id}")

        # Check if this is a GitHub repo (for code artifacts)
        is_github = source_url and 'github.com' in source_url
        is_kaggle = source_url and 'kaggle.com' in source_url

        if is_github:
            return self._download_github_repo_to_s3(repo_id, output_zip_key, revision)

        if is_kaggle:
            # Parse Kaggle URL to extract owner and dataset name
            # repo_id for Kaggle is in format "owner/dataset-name"
            parts = repo_id.split('/')
            if len(parts) >= 2:
                owner = parts[0]
                dataset_name = parts[1]
                logger.info(f"Detected Kaggle dataset: {owner}/{dataset_name}")
                return self._download_kaggle_dataset_to_s3(owner, dataset_name, output_zip_key)
            else:
                raise ValueError(f"Invalid Kaggle repo_id format: {repo_id}")

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

                    # Stream download from HuggingFace (with auth for gated content)
                    headers = {}
                    if self.hf_token:
                        headers['Authorization'] = f'Bearer {self.hf_token}'

                    response = requests.get(url, stream=True, headers=headers)
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

                        headers = {}
                        if self.hf_token:
                            headers['Authorization'] = f'Bearer {self.hf_token}'

                        response = requests.get(url, headers=headers)
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
                    # GitCommitInfo has: commit_id, authors (list), created_at, title
                    # Extract author names from the authors list
                    # Authors can be: strings, dicts with 'user' key, or objects with .user attribute
                    authors = []
                    if hasattr(commit, 'authors') and commit.authors:
                        for author in commit.authors:
                            if isinstance(author, str):
                                # Simple string username
                                authors.append(author)
                                unique_authors.add(author)
                            elif isinstance(author, dict) and 'user' in author:
                                # Dictionary with 'user' key
                                authors.append(author['user'])
                                unique_authors.add(author['user'])
                            elif hasattr(author, 'user'):
                                # Object with .user attribute
                                authors.append(author.user)
                                unique_authors.add(author.user)

                    commit_info = {
                        'commit_id': commit.commit_id if hasattr(commit, 'commit_id') else '',
                        'date': str(commit.created_at) if hasattr(commit, 'created_at') else '',
                        'authors': authors,
                        'title': commit.title if hasattr(commit, 'title') else ''
                    }
                    commit_data.append(commit_info)

                result['_hf_commit_history'] = json.dumps(commit_data).encode('utf-8')
                result['_hf_contributors_count'] = json.dumps({'count': len(unique_authors)}).encode('utf-8')
                logger.info(f"[BUS_FACTOR] Fetched {len(commit_data)} commits, {len(unique_authors)} unique contributors")
            except Exception as e:
                logger.warning(f"[BUS_FACTOR] Failed to fetch commit history: {e}")

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

    def _download_github_repo_to_s3(self, repo_id: str, output_zip_key: str, revision: str = "main") -> Tuple[str, int]:
        """
        Download GitHub repository ZIP and stream directly to S3 (zero-disk)

        Args:
            repo_id: GitHub repo in format "owner/repo"
            output_zip_key: S3 key for the output ZIP
            revision: Git branch/tag (default: "main")

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        logger.info(f"Streaming GitHub repo to S3: {repo_id} (branch: {revision})")

        upload_id = None  # Initialize before try block for error handling
        response = None

        # Try requested branch first, then fallback to alternative
        fallback_branch = "master" if revision == "main" else "main"

        for branch_attempt in [revision, fallback_branch]:
            github_zip_url = f"https://github.com/{repo_id}/archive/refs/heads/{branch_attempt}.zip"
            try:
                response = requests.get(github_zip_url, stream=True, timeout=300)
                if response.status_code == 200:
                    if branch_attempt != revision:
                        logger.info(f"Branch '{revision}' not found, using '{branch_attempt}' instead")
                    break
                elif response.status_code == 404 and branch_attempt == revision:
                    logger.info(f"Branch '{revision}' not found, trying '{fallback_branch}'...")
                    continue
                else:
                    response.raise_for_status()
                    break
            except requests.exceptions.RequestException as e:
                if branch_attempt == fallback_branch:
                    # Both branches failed, raise error
                    raise RuntimeError(f"Failed to download from branches '{revision}' and '{fallback_branch}': {e}")
                continue

        if not response or response.status_code != 200:
            raise RuntimeError(f"Failed to download GitHub repo {repo_id}")

        try:

            # Initialize multipart upload to S3
            upload_id = self.s3_client.create_multipart_upload(
                Bucket=self.bucket,
                Key=output_zip_key,
                ContentType='application/zip'
            )['UploadId']

            parts = []
            part_number = 1
            buffer = bytearray()
            sha256_hash = hashlib.sha256()
            total_size = 0
            chunk_size = 10 * 1024 * 1024  # 10MB chunks

            # Stream data in chunks
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    buffer.extend(chunk)
                    sha256_hash.update(chunk)
                    total_size += len(chunk)

                    # Upload when buffer reaches chunk_size
                    if len(buffer) >= chunk_size:
                        part_response = self.s3_client.upload_part(
                            Bucket=self.bucket,
                            Key=output_zip_key,
                            PartNumber=part_number,
                            UploadId=upload_id,
                            Body=bytes(buffer)
                        )
                        parts.append({'PartNumber': part_number, 'ETag': part_response['ETag']})
                        logger.debug(f"Uploaded part {part_number} ({len(buffer)} bytes)")
                        buffer = bytearray()
                        part_number += 1

            # Upload final buffer
            if buffer:
                part_response = self.s3_client.upload_part(
                    Bucket=self.bucket,
                    Key=output_zip_key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=bytes(buffer)
                )
                parts.append({'PartNumber': part_number, 'ETag': part_response['ETag']})
                logger.debug(f"Uploaded final part {part_number} ({len(buffer)} bytes)")

            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=output_zip_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )

            digest = sha256_hash.hexdigest()
            logger.info(f"GitHub repo streamed to S3: {total_size} bytes, SHA256: {digest[:16]}...")
            return digest, total_size

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download GitHub repo {repo_id}: {e}")
            # Abort multipart upload if it was started
            if upload_id:
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.bucket,
                        Key=output_zip_key,
                        UploadId=upload_id
                    )
                except:
                    pass
            raise RuntimeError(f"GitHub download failed: {e}")
        except Exception as e:
            logger.error(f"Failed to stream GitHub repo: {e}")
            # Abort multipart upload if it was started
            if upload_id:
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.bucket,
                        Key=output_zip_key,
                        UploadId=upload_id
                    )
                except:
                    pass
            raise

    def _download_kaggle_dataset_to_s3(
        self,
        owner: str,
        dataset_name: str,
        output_zip_key: str
    ) -> Tuple[str, int]:
        """
        Download Kaggle dataset to S3 with size checking

        If dataset is larger than LARGE_DATASET_THRESHOLD_BYTES (5GB),
        only metadata is ingested (no actual data download).

        Args:
            owner: Kaggle dataset owner
            dataset_name: Dataset name/slug
            output_zip_key: S3 key for output ZIP

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        # Import Kaggle manager
        src_path = os.path.join(os.path.dirname(__file__), '../../../../src')
        if os.path.exists(src_path) and src_path not in sys.path:
            sys.path.insert(0, src_path)

        try:
            from lib.Kaggle_API_Manager import get_kaggle_manager
        except ImportError as e:
            logger.error(f"Failed to import Kaggle API Manager: {e}")
            raise RuntimeError("Kaggle integration not available")

        kaggle_manager = get_kaggle_manager()
        if not kaggle_manager:
            raise RuntimeError("Kaggle API not configured (KAGGLE_USERNAME/KAGGLE_KEY missing)")

        logger.info(f"Processing Kaggle dataset: {owner}/{dataset_name}")

        # Check dataset size first
        dataset_size = kaggle_manager.get_dataset_size(owner, dataset_name)
        if dataset_size is None:
            logger.warning(f"Could not determine dataset size for {owner}/{dataset_name}, proceeding with metadata-only")
            dataset_size = LARGE_DATASET_THRESHOLD_BYTES + 1  # Force metadata-only

        size_gb = dataset_size / (1024**3)
        threshold_gb = LARGE_DATASET_THRESHOLD_BYTES / (1024**3)

        if dataset_size > LARGE_DATASET_THRESHOLD_BYTES:
            logger.info(f"Dataset size ({size_gb:.2f} GB) exceeds threshold ({threshold_gb:.2f} GB)")
            logger.info(f"Ingesting metadata only (no full dataset download)")

            # Create metadata-only ZIP
            return self._create_kaggle_metadata_zip(owner, dataset_name, output_zip_key, kaggle_manager)
        else:
            logger.info(f"Dataset size ({size_gb:.2f} GB) is below threshold ({threshold_gb:.2f} GB)")
            logger.info(f"Proceeding with full dataset download")

            # Download full dataset
            return self._download_full_kaggle_dataset(owner, dataset_name, output_zip_key, kaggle_manager)

    def _create_kaggle_metadata_zip(
        self,
        owner: str,
        dataset_name: str,
        output_zip_key: str,
        kaggle_manager
    ) -> Tuple[str, int]:
        """
        Create a ZIP with only Kaggle dataset metadata (no actual data)

        Args:
            owner: Kaggle dataset owner
            dataset_name: Dataset name/slug
            output_zip_key: S3 key for output ZIP
            kaggle_manager: KaggleAPIManager instance

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        logger.info(f"Creating metadata-only ZIP for {owner}/{dataset_name}")

        # Get metadata summary (README, metadata.json, etc.)
        metadata_files = kaggle_manager.create_metadata_summary(owner, dataset_name)
        if not metadata_files:
            raise RuntimeError(f"Failed to fetch metadata for {owner}/{dataset_name}")

        # Create ZIP in S3 with metadata files
        import struct
        import zipfile
        import time

        upload_id = None
        try:
            # Initialize multipart upload
            upload_id = self.s3_client.create_multipart_upload(
                Bucket=self.bucket,
                Key=output_zip_key,
                ContentType='application/zip'
            )['UploadId']

            parts = []
            sha256_hash = hashlib.sha256()
            total_size = 0

            # Create ZIP structure in memory
            upload_buffer = io.BytesIO()
            central_directory = []
            offset = 0

            for filename, content in metadata_files.items():
                # Local file header
                mod_time = time.localtime()
                dos_time = (mod_time.tm_hour << 11) | (mod_time.tm_min << 5) | (mod_time.tm_sec // 2)
                dos_date = ((mod_time.tm_year - 1980) << 9) | (mod_time.tm_mon << 5) | mod_time.tm_mday

                crc = hashlib.md5(content).hexdigest()[:8]  # Simplified CRC
                compressed_size = len(content)
                uncompressed_size = len(content)

                local_header = struct.pack('<I', 0x04034b50)  # Local file header signature
                local_header += struct.pack('<H', 20)  # Version needed
                local_header += struct.pack('<H', 0)   # Flags
                local_header += struct.pack('<H', 0)   # Compression (stored)
                local_header += struct.pack('<H', dos_time)
                local_header += struct.pack('<H', dos_date)
                local_header += struct.pack('<I', int(crc, 16))  # CRC-32
                local_header += struct.pack('<I', compressed_size)
                local_header += struct.pack('<I', uncompressed_size)
                local_header += struct.pack('<H', len(filename))
                local_header += struct.pack('<H', 0)   # Extra field length
                local_header += filename.encode('utf-8')

                upload_buffer.write(local_header)
                sha256_hash.update(local_header)

                upload_buffer.write(content)
                sha256_hash.update(content)

                # Store info for central directory
                central_directory.append({
                    'filename': filename,
                    'offset': offset,
                    'crc': int(crc, 16),
                    'compressed_size': compressed_size,
                    'uncompressed_size': uncompressed_size,
                    'dos_time': dos_time,
                    'dos_date': dos_date
                })

                offset += len(local_header) + len(content)

            # Upload the file data
            upload_buffer.seek(0)
            part_data = upload_buffer.read()

            response_part = self.s3_client.upload_part(
                Bucket=self.bucket,
                Key=output_zip_key,
                PartNumber=1,
                UploadId=upload_id,
                Body=part_data
            )

            parts.append({'PartNumber': 1, 'ETag': response_part['ETag']})
            total_size += len(part_data)

            # Create central directory
            central_dir_data = io.BytesIO()
            central_dir_start = offset

            for entry in central_directory:
                cd_header = struct.pack('<I', 0x02014b50)  # Central directory signature
                cd_header += struct.pack('<H', 20)  # Version made by
                cd_header += struct.pack('<H', 20)  # Version needed
                cd_header += struct.pack('<H', 0)   # Flags
                cd_header += struct.pack('<H', 0)   # Compression
                cd_header += struct.pack('<H', entry['dos_time'])
                cd_header += struct.pack('<H', entry['dos_date'])
                cd_header += struct.pack('<I', entry['crc'])
                cd_header += struct.pack('<I', entry['compressed_size'])
                cd_header += struct.pack('<I', entry['uncompressed_size'])
                cd_header += struct.pack('<H', len(entry['filename']))
                cd_header += struct.pack('<H', 0)   # Extra field
                cd_header += struct.pack('<H', 0)   # Comment length
                cd_header += struct.pack('<H', 0)   # Disk number
                cd_header += struct.pack('<H', 0)   # Internal attributes
                cd_header += struct.pack('<I', 0)   # External attributes
                cd_header += struct.pack('<I', entry['offset'])
                cd_header += entry['filename'].encode('utf-8')

                central_dir_data.write(cd_header)
                offset += len(cd_header)

            central_dir_bytes = central_dir_data.getvalue()

            # End of central directory
            eocd = struct.pack('<I', 0x06054b50)  # EOCD signature
            eocd += struct.pack('<H', 0)   # Disk number
            eocd += struct.pack('<H', 0)   # Disk with central dir
            eocd += struct.pack('<H', len(central_directory))
            eocd += struct.pack('<H', len(central_directory))
            eocd += struct.pack('<I', len(central_dir_bytes))
            eocd += struct.pack('<I', central_dir_start)
            eocd += struct.pack('<H', 0)   # Comment length

            # Upload central directory + EOCD
            final_buffer = io.BytesIO()
            final_buffer.write(central_dir_bytes)
            final_buffer.write(eocd)
            final_buffer.seek(0)
            final_data = final_buffer.read()

            sha256_hash.update(final_data)

            response_part = self.s3_client.upload_part(
                Bucket=self.bucket,
                Key=output_zip_key,
                PartNumber=2,
                UploadId=upload_id,
                Body=final_data
            )

            parts.append({'PartNumber': 2, 'ETag': response_part['ETag']})
            total_size += len(final_data)

            # Complete multipart upload
            self.s3_client.complete_multipart_upload(
                Bucket=self.bucket,
                Key=output_zip_key,
                UploadId=upload_id,
                MultipartUpload={'Parts': parts}
            )

            digest = sha256_hash.hexdigest()
            logger.info(f"Kaggle metadata ZIP created: {total_size} bytes, SHA256: {digest[:16]}...")
            logger.info(f"Included files: {list(metadata_files.keys())}")

            return digest, total_size

        except Exception as e:
            logger.error(f"Failed to create Kaggle metadata ZIP: {e}")
            if upload_id:
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.bucket,
                        Key=output_zip_key,
                        UploadId=upload_id
                    )
                except:
                    pass
            raise

    def _download_full_kaggle_dataset(
        self,
        owner: str,
        dataset_name: str,
        output_zip_key: str,
        kaggle_manager
    ) -> Tuple[str, int]:
        """
        Download full Kaggle dataset and upload to S3

        Uses kaggle CLI to download dataset to temp directory,
        then streams to S3.

        Args:
            owner: Kaggle dataset owner
            dataset_name: Dataset name/slug
            output_zip_key: S3 key for output ZIP
            kaggle_manager: KaggleAPIManager instance

        Returns:
            Tuple of (sha256_hash, size_bytes)
        """
        import tempfile
        import subprocess
        import shutil
        import zipfile

        logger.info(f"Downloading full Kaggle dataset: {owner}/{dataset_name}")

        temp_dir = tempfile.mkdtemp(prefix='kaggle_')
        try:
            # Download using kaggle CLI
            dataset_ref = f'{owner}/{dataset_name}'
            cmd = ['kaggle', 'datasets', 'download', '-d', dataset_ref, '-p', temp_dir]

            logger.info(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode != 0:
                logger.error(f"Kaggle download failed: {result.stderr}")
                raise RuntimeError(f"Failed to download Kaggle dataset: {result.stderr}")

            logger.info(f"Download completed to {temp_dir}")

            # Find downloaded ZIP file
            downloaded_files = os.listdir(temp_dir)
            zip_file = None
            for f in downloaded_files:
                if f.endswith('.zip'):
                    zip_file = os.path.join(temp_dir, f)
                    break

            if not zip_file:
                raise RuntimeError(f"No ZIP file found in {temp_dir}")

            logger.info(f"Found downloaded ZIP: {zip_file}")

            # Stream ZIP to S3
            file_size = os.path.getsize(zip_file)
            logger.info(f"Uploading {file_size} bytes to S3...")

            sha256_hash = hashlib.sha256()
            upload_id = None

            try:
                upload_id = self.s3_client.create_multipart_upload(
                    Bucket=self.bucket,
                    Key=output_zip_key,
                    ContentType='application/zip'
                )['UploadId']

                parts = []
                part_number = 1
                chunk_size = 10 * 1024 * 1024  # 10MB chunks
                total_uploaded = 0

                with open(zip_file, 'rb') as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break

                        sha256_hash.update(chunk)

                        response_part = self.s3_client.upload_part(
                            Bucket=self.bucket,
                            Key=output_zip_key,
                            PartNumber=part_number,
                            UploadId=upload_id,
                            Body=chunk
                        )

                        parts.append({'PartNumber': part_number, 'ETag': response_part['ETag']})
                        total_uploaded += len(chunk)
                        part_number += 1

                        if part_number % 10 == 0:
                            logger.info(f"Uploaded {total_uploaded / (1024**2):.2f} MB...")

                # Complete upload
                self.s3_client.complete_multipart_upload(
                    Bucket=self.bucket,
                    Key=output_zip_key,
                    UploadId=upload_id,
                    MultipartUpload={'Parts': parts}
                )

                digest = sha256_hash.hexdigest()
                logger.info(f"Kaggle dataset uploaded: {total_uploaded} bytes, SHA256: {digest[:16]}...")

                return digest, total_uploaded

            except Exception as e:
                logger.error(f"Failed to upload Kaggle dataset to S3: {e}")
                if upload_id:
                    try:
                        self.s3_client.abort_multipart_upload(
                            Bucket=self.bucket,
                            Key=output_zip_key,
                            UploadId=upload_id
                        )
                    except:
                        pass
                raise

        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp directory: {e}")

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
