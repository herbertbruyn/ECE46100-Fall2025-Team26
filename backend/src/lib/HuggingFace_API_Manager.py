import os
import re
import logging
import json
from typing import Optional
from huggingface_hub import DatasetInfo, HfApi, ModelInfo, hf_hub_download


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
        """Converts a Hugging Face model link to a model ID."""
        match = re.search(r"huggingface\.co/([^/]+/[^/]+)", model_link)
        if match:
            return match.group(1)
        raise ValueError(f"Invalid model link: {model_link}")

    @staticmethod
    def dataset_link_to_id(dataset_link: str) -> str:
        """Converts a Hugging Face dataset link to a dataset ID."""
        match = re.search(
            r"huggingface\.co/datasets/([^/]+/[^/]+)", dataset_link
        )
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

    
    def get_model_config(self, model_id: str) -> Optional[dict]:
        """Get model configuration from Hugging Face."""
        try:
            config_path = hf_hub_download(
                repo_id=model_id,
                filename="config.json",
                token=self.hf_token,
            )
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Could not get model config for {model_id}: {e}")
            return None

    
    def extract_parent_model(self, config: Optional[dict]) -> Optional[str]:
        """Extract parent model from model configuration."""
        if not config:
            return None

        for field in ['base_model_name_or_path', '_name_or_path', 'base_model']:
            if field in config:
                parent_model = config[field]
                if isinstance(parent_model, str) and parent_model:
                    return parent_model

        return None
        
        