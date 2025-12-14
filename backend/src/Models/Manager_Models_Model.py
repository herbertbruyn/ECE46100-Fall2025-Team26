import logging
from huggingface_hub import (
    DatasetCardData,
    DatasetInfo,
    ModelCardData,
    ModelInfo,
)
from typing import List, Optional

from .Model import Model


class ModelManager(Model):
    def __init__(self) -> None:
        super().__init__()
        self.id: str = ""
        self.info: Optional[ModelInfo] = None
        self.card: Optional[ModelCardData] = None
        self.readme_path: Optional[str] = None

        self.dataset_ids: List[str] = []
        self.dataset_infos: dict[str, DatasetInfo] = {}
        self.dataset_cards: dict[str, Optional[DatasetCardData]] = {}

        self.repo_metadata: dict = {}
        self.repo_contents: list = []
        self.repo_contributors: list = []
        self.repo_commit_history: list = []

    def where(
        self,
        model_link: str,
        dataset_links: Optional[List[str]] = None,
        code_link: Optional[str] = None
    ) -> 'ModelManager':
        model_data = self

        model_data.id = self.huggingface_manager.model_link_to_id(model_link)
        model_data.info = self.huggingface_manager.get_model_info(
            model_data.id
        )
        model_data.card = (
            model_data.info.card_data if model_data.info else None
        )

        model_data.readme_path = (
            self.huggingface_manager.download_model_readme(model_data.id)
        )

        if dataset_links is not None:
            for dataset_link in dataset_links:
                try:
                    dataset_id = self.huggingface_manager.dataset_link_to_id(
                        dataset_link
                    )
                    model_data.dataset_ids.append(dataset_id)
                except ValueError as e:
                    logging.warning(f"Skipping invalid dataset link: {e}")

        for dataset_id in model_data.dataset_ids:
            try:
                dataset_info = self.huggingface_manager.get_dataset_info(
                    dataset_id
                )
                model_data.dataset_infos[dataset_id] = dataset_info
                model_data.dataset_cards[dataset_id] = dataset_info.card_data
            except Exception as e:
                logging.warning(f"Failed to fetch dataset {dataset_id}: {e}")

        owner, repo = None, None
        if code_link is not None:
            logging.info(f"Processing code_link: {code_link}")
            try:
                owner, repo = self.github_manager.code_link_to_repo(code_link)
                logging.info(f"Extracted owner='{owner}', repo='{repo}'")
            except ValueError as e:
                logging.warning(f"Invalid code link provided: {e}")
        else:
            logging.info("No code_link provided")

        logging.info(f"Calling _fetch_github_data with owner='{owner}', repo='{repo}'")
        self._fetch_github_data(model_data, owner, repo)

        return model_data

    def _fetch_github_data(self, model_data, owner: str, repo: str) -> None:
        logging.info(f"_fetch_github_data called: owner='{owner}', repo='{repo}'")
        
        if not (owner and repo):
            logging.warning("No owner/repo provided, skipping GitHub data fetch")
            model_data.repo_metadata = {}
            model_data.repo_contents = []
            model_data.repo_contributors = []
            model_data.repo_commit_history = []
            return

        logging.info(f"Fetching GitHub data for {owner}/{repo}")

        try:
            model_data.repo_metadata = (
                self.github_manager.get_repo_info(owner, repo)
            )
            logging.info(f"Successfully fetched repo metadata")
        except Exception as e:
            logging.warning(f"Failed to fetch repo metadata: {e}")
            model_data.repo_metadata = {}

        try:
            model_data.repo_contents = (
                self.github_manager.get_repo_contents(owner, repo)
            )
            logging.info(f"Successfully fetched repo contents")
        except Exception as e:
            logging.warning(f"Failed to fetch repo contents: {e}")
            model_data.repo_contents = []

        try:
            repo_contributors_result = self.github_manager.github_request(
                path=f"/repos/{owner}/{repo}/contributors"
            )
            model_data.repo_contributors = (
                repo_contributors_result
                if isinstance(repo_contributors_result, list)
                else []
            )
            logging.info(f"Successfully fetched {len(model_data.repo_contributors)} contributors")
        except Exception as e:
            logging.warning(f"Failed to fetch repo contributors: {e}")
            model_data.repo_contributors = []

        try:
            repo_commits_result = self.github_manager.github_request(
                path=f"/repos/{owner}/{repo}/commits",
                params={"per_page": 10}
            )
            model_data.repo_commit_history = (
                repo_commits_result
                if isinstance(repo_commits_result, list)
                else []
            )
            logging.info(f"Successfully fetched {len(model_data.repo_commit_history)} commits")
        except Exception as e:
            logging.warning(f"Failed to fetch repo commits: {e}")
            model_data.repo_commit_history = []
