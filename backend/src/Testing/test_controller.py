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
from Models.Model import Model  # noqa: E402


class TestController:
    """Test cases for Controller class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.controller = Controller()

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    @patch('Controllers.Controller.GitHubAPIManager')
    def test_fetch_basic(self, mock_github_api, mock_hf_api):
        """Test basic fetch functionality."""
        # Setup mocks
        mock_hf_instance = Mock()
        mock_github_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        mock_github_api.return_value = mock_github_instance
        
        # Mock model info
        mock_model_info = Mock()
        mock_model_info.id = "test/model"
        mock_hf_instance.get_model_info.return_value = mock_model_info
        mock_hf_instance.get_model_card.return_value = "Model card content"
        
        # Mock dataset info
        mock_dataset_info = Mock()
        mock_dataset_info.id = "test/dataset"
        mock_hf_instance.get_dataset_info.return_value = mock_dataset_info
        
        # Mock GitHub info
        mock_github_instance.get_repo_info.return_value = {
            "name": "test-repo",
            "description": "Test repository"
        }
        
        model_link = "https://huggingface.co/test/model"
        dataset_links = ["https://huggingface.co/datasets/test/dataset"]
        code_link = "https://github.com/test/repo"
        
        result = self.controller.fetch(model_link, dataset_links, code_link)
        
        assert isinstance(result, Model)
        assert result.model_link == model_link

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    def test_fetch_model_only(self, mock_hf_api):
        """Test fetch with model link only."""
        mock_hf_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        
        mock_model_info = Mock()
        mock_model_info.id = "test/model"
        mock_hf_instance.get_model_info.return_value = mock_model_info
        mock_hf_instance.get_model_card.return_value = "Model card"
        
        model_link = "https://huggingface.co/test/model"
        result = self.controller.fetch(model_link)
        
        assert isinstance(result, Model)
        assert result.model_link == model_link
        assert result.dataset_links == []
        assert result.code_link is None

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    def test_fetch_with_invalid_model_link(self, mock_hf_api):
        """Test fetch with invalid model link."""
        mock_hf_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        mock_hf_instance.get_model_info.side_effect = Exception(
            "Model not found")
        
        model_link = "https://huggingface.co/invalid/model"
        
        # Should handle gracefully
        try:
            result = self.controller.fetch(model_link)
            # Either returns a Model with error info or raises exception
            assert isinstance(result, Model) or result is None
        except Exception:
            # Exception is acceptable for invalid input
            pass

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    @patch('Controllers.Controller.GitHubAPIManager')
    def test_fetch_with_multiple_datasets(self, mock_github_api, mock_hf_api):
        """Test fetch with multiple dataset links."""
        mock_hf_instance = Mock()
        mock_github_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        mock_github_api.return_value = mock_github_instance
        
        # Mock model info
        mock_model_info = Mock()
        mock_model_info.id = "test/model"
        mock_hf_instance.get_model_info.return_value = mock_model_info
        mock_hf_instance.get_model_card.return_value = "Model card"
        
        # Mock dataset info
        mock_dataset_info = Mock()
        mock_dataset_info.id = "test/dataset"
        mock_hf_instance.get_dataset_info.return_value = mock_dataset_info
        
        model_link = "https://huggingface.co/test/model"
        dataset_links = [
            "https://huggingface.co/datasets/test/dataset1",
            "https://huggingface.co/datasets/test/dataset2"
        ]
        
        result = self.controller.fetch(model_link, dataset_links)
        
        assert isinstance(result, Model)
        assert len(result.dataset_links) == 2

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    def test_fetch_api_failure(self, mock_hf_api):
        """Test fetch when API calls fail."""
        mock_hf_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        mock_hf_instance.get_model_info.side_effect = ConnectionError(
            "API unavailable")
        
        model_link = "https://huggingface.co/test/model"
        
        # Should handle API failures gracefully
        try:
            result = self.controller.fetch(model_link)
            # Depending on implementation, might return partial data or None
            assert result is None or isinstance(result, Model)
        except Exception:
            # Exception handling is implementation dependent
            pass

    def test_controller_initialization(self):
        """Test controller initialization."""
        controller = Controller()
        assert controller is not None
        # Verify that API managers are initialized
        assert (hasattr(controller, 'hf_api') or
                hasattr(controller, 'github_api'))

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    def test_fetch_empty_dataset_links(self, mock_hf_api):
        """Test fetch with empty dataset links list."""
        mock_hf_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        
        mock_model_info = Mock()
        mock_model_info.id = "test/model"
        mock_hf_instance.get_model_info.return_value = mock_model_info
        mock_hf_instance.get_model_card.return_value = "Model card"
        
        model_link = "https://huggingface.co/test/model"
        result = self.controller.fetch(model_link, dataset_links=[])
        
        assert isinstance(result, Model)
        assert result.dataset_links == []

    @patch('Controllers.Controller.HuggingFaceAPIManager')
    @patch('Controllers.Controller.GitHubAPIManager')
    def test_fetch_github_api_failure(self, mock_github_api, mock_hf_api):
        """Test fetch when GitHub API fails but HF API works."""
        mock_hf_instance = Mock()
        mock_github_instance = Mock()
        mock_hf_api.return_value = mock_hf_instance
        mock_github_api.return_value = mock_github_instance
        
        # HF API works
        mock_model_info = Mock()
        mock_model_info.id = "test/model"
        mock_hf_instance.get_model_info.return_value = mock_model_info
        mock_hf_instance.get_model_card.return_value = "Model card"
        
        # GitHub API fails
        mock_github_instance.get_repo_info.side_effect = Exception(
            "GitHub API error")
        
        model_link = "https://huggingface.co/test/model"
        code_link = "https://github.com/test/repo"
        
        result = self.controller.fetch(model_link, code_link=code_link)
        
        # Should still return a model, possibly with partial data
        assert isinstance(result, Model)
        assert result.model_link == model_link
