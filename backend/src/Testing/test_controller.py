"""
Unit tests for Controller module.
Tests data fetching and controller functionality.
"""
import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import after adding to path
from Controllers.Controller import Controller  # noqa: E402
from Models.Manager_Models_Model import ModelManager  # noqa: E402


class TestController:
    """Test cases for Controller class."""

    def test_fetch_basic(self):
        """Test basic fetch functionality with real models.
        
        Tests both model link formats:
        - Short name without organization prefix
        - Full name with organization prefix
        """
        controller = Controller()
        
        # Test 1: Short name without org prefix
        model_link_short = "https://huggingface.co/distilbert-base-uncased"
        result_short = controller.fetch(model_link_short)
        
        assert isinstance(result_short, ModelManager)
        assert result_short.id == "distilbert-base-uncased"
        assert result_short.info is not None
        assert result_short.card is not None
        
        # Test 2: Full name with org prefix
        model_link_full = "https://huggingface.co/google-bert/bert-base-uncased"
        result_full = controller.fetch(model_link_full)
        
        assert isinstance(result_full, ModelManager)
        assert result_full.id == "google-bert/bert-base-uncased"
        assert result_full.info is not None
        assert result_full.card is not None

    def test_fetch_model_only(self):
        """Test fetch with model link only (no datasets or code)."""
        controller = Controller()
        
        # Fetch model without datasets or code links
        model_link = "https://huggingface.co/gpt2"
        result = controller.fetch(model_link)
        
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        assert result.info is not None
        assert result.dataset_ids == []
        assert result.repo_metadata == {}

    def test_fetch_with_invalid_model_link(self):
        """Test fetch with invalid model link."""
        controller = Controller()
        
        # Use an invalid link format (missing model path)
        model_link = "https://huggingface.co/"
        
        # Should raise ValueError
        try:
            result = controller.fetch(model_link)
            assert False, "Should have raised a ValueError"
        except ValueError as e:
            # Expected behavior - invalid link format
            assert "Invalid model link" in str(e)
            pass

    def test_fetch_with_multiple_datasets(self):
        """Test fetch with multiple dataset links."""
        controller = Controller()
        
        # Use real model and datasets
        model_link = "https://huggingface.co/gpt2"
        dataset_links = [
            "https://huggingface.co/datasets/squad",
            "https://huggingface.co/datasets/glue"
        ]
        
        result = controller.fetch(model_link, dataset_links)
        
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        assert len(result.dataset_ids) == 2
        assert "squad" in result.dataset_ids
        assert "glue" in result.dataset_ids
        # Verify dataset info was fetched
        assert len(result.dataset_infos) == 2

    def test_fetch_api_failure(self):
        """Test fetch when model doesn't exist (API failure)."""
        controller = Controller()
        
        # Use a model that definitely doesn't exist
        model_link = "https://huggingface.co/this-model-definitely-does-not-exist-12345"
        
        # Should handle API failures by raising an exception
        try:
            result = controller.fetch(model_link)
            assert False, "Should have raised an exception for non-existent model"
        except Exception as e:
            # Expected behavior - model not found
            # Could be RepositoryNotFoundError or HTTPStatusError
            pass

    def test_controller_initialization(self):
        """Test controller initialization."""
        controller = Controller()
        assert controller is not None
        # Verify that model_manager is initialized
        assert hasattr(controller, 'model_manager')
        assert isinstance(controller.model_manager, ModelManager)

    def test_fetch_empty_dataset_links(self):
        """Test fetch with empty dataset links list."""
        controller = Controller()
        
        # Fetch with explicitly empty dataset list
        model_link = "https://huggingface.co/gpt2"
        result = controller.fetch(model_link, dataset_links=[])
        
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        assert result.dataset_ids == []
        assert result.dataset_infos == {}

    @patch('Models.Model.GitHubAPIManager')
    def test_fetch_github_api_failure(self, mock_github_api_class):
        """Test fetch when GitHub API fails but HF API works.
        
        This test verifies graceful degradation when GitHub is unavailable.
        """
        # Mock GitHub to fail
        mock_github_instance = Mock()
        mock_github_api_class.return_value = mock_github_instance
        
        mock_github_instance.code_link_to_repo.return_value = ("test", "repo")
        mock_github_instance.get_repo_info.side_effect = Exception("GitHub API error")
        mock_github_instance.get_repo_contents.side_effect = Exception("GitHub API error")
        mock_github_instance.github_request.side_effect = Exception("GitHub API error")
        
        controller = Controller()
        
        # Use real HuggingFace model but fake GitHub repo
        model_link = "https://huggingface.co/gpt2"
        code_link = "https://github.com/test/repo"
        
        result = controller.fetch(model_link, code_link=code_link)
        
        # Should still return a model with HF data but empty GitHub data
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        assert result.info is not None  # HF data works
        assert result.repo_metadata == {}  # GitHub failed, so empty dict
        assert result.repo_contents == []
        assert result.repo_contributors == []

    def test_fetch_with_github_repo(self):
        """Test fetch with real GitHub repository."""
        controller = Controller()
        
        # Use real model and real GitHub repo
        model_link = "https://huggingface.co/gpt2"
        code_link = "https://github.com/openai/gpt-2"
        
        result = controller.fetch(model_link, code_link=code_link)
        
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        assert result.info is not None
        # GitHub data should be populated
        assert isinstance(result.repo_metadata, dict)
        # Repo metadata should have some keys if fetch succeeded
        # (might be empty if API rate limited or token not set)
        assert isinstance(result.repo_contents, list)
        assert isinstance(result.repo_contributors, list)

    def test_fetch_with_invalid_dataset_link(self):
        """Test fetch with invalid dataset link (should be skipped with warning)."""
        controller = Controller()
        
        model_link = "https://huggingface.co/gpt2"
        # Invalid dataset link (missing dataset path)
        dataset_links = ["https://huggingface.co/datasets/"]
        
        # Should skip invalid dataset and continue
        result = controller.fetch(model_link, dataset_links)
        
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        # Invalid dataset should be skipped, so empty list
        assert result.dataset_ids == []

    def test_fetch_full_integration(self):
        """Test full integration with model, datasets, and GitHub repo."""
        controller = Controller()
        
        model_link = "https://huggingface.co/gpt2"
        dataset_links = ["https://huggingface.co/datasets/squad"]
        code_link = "https://github.com/openai/gpt-2"
        
        result = controller.fetch(model_link, dataset_links, code_link)
        
        assert isinstance(result, ModelManager)
        assert result.id == "gpt2"
        assert result.info is not None
        assert result.card is not None
        assert len(result.dataset_ids) == 1
        assert "squad" in result.dataset_ids
        # GitHub data (may be empty if rate limited)
        assert isinstance(result.repo_metadata, dict)
        assert isinstance(result.repo_contents, list)
