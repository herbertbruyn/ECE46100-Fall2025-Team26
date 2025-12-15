"""
Kaggle API Manager

Handles interaction with Kaggle datasets API:
- Authentication using KAGGLE_USERNAME and KAGGLE_KEY environment variables
- Dataset metadata extraction
- Size checking to avoid downloading large datasets
- URL parsing and validation
"""
import os
import re
import json
import logging
from typing import Optional, Dict, Tuple
import requests

logger = logging.getLogger(__name__)


class KaggleAPIManager:
    """Manager for Kaggle API interactions"""

    def __init__(self):
        """Initialize with Kaggle credentials from environment"""
        self.username = os.getenv('KAGGLE_USERNAME')
        self.key = os.getenv('KAGGLE_KEY')

        if not self.username or not self.key:
            logger.warning("KAGGLE_USERNAME or KAGGLE_KEY not set - Kaggle datasets will not be available")
            self.authenticated = False
        else:
            self.authenticated = True
            logger.info(f"Kaggle API Manager initialized for user: {self.username}")

        self.base_url = "https://www.kaggle.com/api/v1"

    def is_kaggle_url(self, url: str) -> bool:
        """Check if URL is a Kaggle dataset URL"""
        return 'kaggle.com/datasets/' in url or 'kaggle.com/competitions/' in url

    def parse_kaggle_url(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Parse Kaggle URL to extract owner and dataset name

        Examples:
            https://www.kaggle.com/datasets/owner/dataset-name -> ('owner', 'dataset-name')
            https://kaggle.com/datasets/owner/dataset-name -> ('owner', 'dataset-name')
            https://www.kaggle.com/competitions/competition-name -> ('competitions', 'competition-name')

        Returns:
            Tuple of (owner, dataset_name) or None if invalid
        """
        url = url.rstrip('/')

        # Match dataset URLs
        dataset_match = re.search(r'kaggle\.com/datasets/([^/]+)/([^/?]+)', url)
        if dataset_match:
            return dataset_match.group(1), dataset_match.group(2)

        # Match competition URLs (treat as datasets)
        comp_match = re.search(r'kaggle\.com/competitions/([^/?]+)', url)
        if comp_match:
            return 'competitions', comp_match.group(1)

        return None

    def get_dataset_metadata(self, owner: str, dataset_name: str) -> Optional[Dict]:
        """
        Fetch dataset metadata from Kaggle API

        Args:
            owner: Dataset owner username
            dataset_name: Dataset slug/name

        Returns:
            Dictionary with metadata or None if failed
        """
        if not self.authenticated:
            logger.error("Cannot fetch metadata - Kaggle credentials not configured")
            return None

        try:
            # API endpoint for dataset metadata
            url = f"{self.base_url}/datasets/view/{owner}/{dataset_name}"

            response = requests.get(
                url,
                auth=(self.username, self.key),
                timeout=30
            )

            if response.status_code == 200:
                metadata = response.json()
                logger.info(f"Fetched metadata for {owner}/{dataset_name}")
                return metadata
            else:
                logger.error(f"Failed to fetch Kaggle metadata: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            logger.error(f"Error fetching Kaggle dataset metadata: {e}")
            return None

    def get_dataset_size(self, owner: str, dataset_name: str) -> Optional[int]:
        """
        Get total size of dataset in bytes

        Args:
            owner: Dataset owner username
            dataset_name: Dataset slug/name

        Returns:
            Size in bytes or None if failed
        """
        metadata = self.get_dataset_metadata(owner, dataset_name)
        if not metadata:
            return None

        # Kaggle API returns totalBytes field
        total_bytes = metadata.get('totalBytes', 0)

        if total_bytes:
            logger.info(f"Dataset {owner}/{dataset_name} size: {total_bytes} bytes ({total_bytes / (1024**3):.2f} GB)")
            return total_bytes

        # Fallback: sum up file sizes
        files = metadata.get('datasetFiles', [])
        total_size = sum(f.get('totalBytes', 0) for f in files)

        logger.info(f"Dataset {owner}/{dataset_name} size (from files): {total_size} bytes ({total_size / (1024**3):.2f} GB)")
        return total_size

    def get_dataset_files(self, owner: str, dataset_name: str) -> list:
        """
        Get list of files in the dataset

        Args:
            owner: Dataset owner username
            dataset_name: Dataset slug/name

        Returns:
            List of file dictionaries with name, size, etc.
        """
        metadata = self.get_dataset_metadata(owner, dataset_name)
        if not metadata:
            return []

        files = metadata.get('datasetFiles', [])
        logger.info(f"Dataset {owner}/{dataset_name} has {len(files)} files")

        return files

    def download_dataset(self, owner: str, dataset_name: str, output_path: str) -> bool:
        """
        Download dataset using Kaggle CLI

        Note: This requires kaggle package to be installed

        Args:
            owner: Dataset owner username
            dataset_name: Dataset slug/name
            output_path: Where to save the downloaded files

        Returns:
            True if successful, False otherwise
        """
        if not self.authenticated:
            logger.error("Cannot download - Kaggle credentials not configured")
            return False

        try:
            # Use kaggle CLI via subprocess
            import subprocess

            cmd = [
                'kaggle', 'datasets', 'download',
                '-d', f'{owner}/{dataset_name}',
                '-p', output_path,
                '--unzip'
            ]

            logger.info(f"Downloading Kaggle dataset: {owner}/{dataset_name}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            if result.returncode == 0:
                logger.info(f"Successfully downloaded {owner}/{dataset_name}")
                return True
            else:
                logger.error(f"Failed to download dataset: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error downloading Kaggle dataset: {e}")
            return False

    def create_metadata_summary(self, owner: str, dataset_name: str) -> Optional[Dict[str, bytes]]:
        """
        Create a minimal metadata summary for large datasets

        Instead of downloading the full dataset, we create a summary with:
        - Dataset metadata (description, files list, size, etc.)
        - README-like content from the dataset description

        Args:
            owner: Dataset owner username
            dataset_name: Dataset slug/name

        Returns:
            Dictionary mapping filenames to content bytes
        """
        metadata = self.get_dataset_metadata(owner, dataset_name)
        if not metadata:
            return None

        result = {}

        # Create README from dataset description
        description = metadata.get('description', '')
        title = metadata.get('title', f'{owner}/{dataset_name}')
        subtitle = metadata.get('subtitle', '')

        readme_content = f"# {title}\n\n"
        if subtitle:
            readme_content += f"{subtitle}\n\n"
        if description:
            readme_content += f"## Description\n\n{description}\n\n"

        # Add dataset info
        readme_content += f"## Dataset Information\n\n"
        readme_content += f"- **Owner**: {owner}\n"
        readme_content += f"- **Dataset**: {dataset_name}\n"
        readme_content += f"- **Total Size**: {metadata.get('totalBytes', 0)} bytes\n"
        readme_content += f"- **Files**: {len(metadata.get('datasetFiles', []))}\n"
        readme_content += f"- **URL**: https://www.kaggle.com/datasets/{owner}/{dataset_name}\n\n"

        # Add file list
        files = metadata.get('datasetFiles', [])
        if files:
            readme_content += f"## Files\n\n"
            for file_info in files:
                name = file_info.get('name', 'unknown')
                size = file_info.get('totalBytes', 0)
                readme_content += f"- `{name}` ({size} bytes)\n"

        result['README.md'] = readme_content.encode('utf-8')

        # Create metadata.json with full API response
        result['_kaggle_metadata.json'] = json.dumps(metadata, indent=2).encode('utf-8')

        # Create a dataset_info.json file (similar to HuggingFace format)
        dataset_info = {
            'dataset_name': f'{owner}/{dataset_name}',
            'description': description,
            'title': title,
            'total_bytes': metadata.get('totalBytes', 0),
            'num_files': len(files),
            'files': [
                {
                    'name': f.get('name'),
                    'size': f.get('totalBytes', 0)
                }
                for f in files
            ],
            'source': 'kaggle',
            'url': f'https://www.kaggle.com/datasets/{owner}/{dataset_name}'
        }
        result['dataset_info.json'] = json.dumps(dataset_info, indent=2).encode('utf-8')

        logger.info(f"Created metadata summary for {owner}/{dataset_name} with {len(result)} files")

        return result


# Singleton instance
_kaggle_manager = None

def get_kaggle_manager() -> Optional[KaggleAPIManager]:
    """Get singleton Kaggle API manager instance"""
    global _kaggle_manager
    if _kaggle_manager is None:
        _kaggle_manager = KaggleAPIManager()
    return _kaggle_manager if _kaggle_manager.authenticated else None
