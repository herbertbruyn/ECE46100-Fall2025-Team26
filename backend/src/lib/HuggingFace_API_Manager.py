import os
import re
import logging
from typing import Optional
from huggingface_hub import DatasetInfo, HfApi, ModelInfo


class HuggingFaceAPIManager:
    def __init__(self):
        token = os.getenv("HF_TOKEN")

        # Token is optional for public repositories
        if token:
            logging.info("Using HuggingFace token for authenticated access")
            self.hf_api = HfApi(
                endpoint="https://huggingface.co",
                token=token
            )
        else:
            logging.warning("Using anonymous access to HuggingFace ")
            self.hf_api = HfApi(
                endpoint="https://huggingface.co"
            )
        
        self.hf_token = token

    @staticmethod
    def model_link_to_id(model_link: str) -> str:
        """Converts a Hugging Face model link to a model ID.
        
        Handles both formats:
        - https://huggingface.co/org/model (with organization)
        - https://huggingface.co/model (without organization)
        """
        # Try with organization first (org/model)
        match = re.search(r"huggingface\.co/([^/]+/[^/]+)", model_link)
        if match:
            return match.group(1)
        
        # Try without organization (just model name)
        match = re.search(r"huggingface\.co/([^/]+)$", model_link)
        if match:
            return match.group(1)
        
        raise ValueError(f"Invalid model link: {model_link}")

    @staticmethod
    def dataset_link_to_id(dataset_link: str) -> str:
        """Converts a Hugging Face dataset link to a dataset ID.
        
        Handles both formats:
        - https://huggingface.co/datasets/org/dataset (with organization)
        - https://huggingface.co/datasets/dataset (without organization)
        """
        # Try with organization first (org/dataset)
        match = re.search(
            r"huggingface\.co/datasets/([^/]+/[^/]+)", dataset_link
        )
        if match:
            return match.group(1)
        
        # Try without organization (just dataset name)
        match = re.search(r"huggingface\.co/datasets/([^/]+)$", dataset_link)
        if match:
            return match.group(1)
        
        raise ValueError(f"Invalid dataset link: {dataset_link}")

    def get_model_info(self, model_id: str) -> ModelInfo:
        """Get model information from Hugging Face."""
        return self.hf_api.model_info(model_id)

    def get_dataset_info(self, dataset_id: str) -> DatasetInfo:
        """Get dataset information from Hugging Face."""
        return self.hf_api.dataset_info(dataset_id)

    def download_model_readme(self, model_id: str) -> Optional[str]:
        """Download model README file from Hugging Face."""
        try:
            return self.hf_api.hf_hub_download(
                repo_id=model_id,
                filename="README.md",
            )
        except Exception as e:
            logging.warning(
                f"README.md not found for model {model_id}: {e}"
            )
            return None

    def download_dataset_readme(self, dataset_id: str) -> Optional[str]:
        """Download dataset README file from Hugging Face."""
        try:
            return self.hf_api.hf_hub_download(
                repo_id=dataset_id,
                filename="README.md",
                repo_type="dataset"
            )
        except Exception as e:
            logging.warning(
                f"README.md not found for dataset {dataset_id}: {e}"
            )
            return None
