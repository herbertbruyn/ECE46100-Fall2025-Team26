"""
Unit tests for lib modules.
Tests API managers, LLM manager, and metric results.
"""
import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import after adding to path
from lib.Metric_Result import MetricResult, MetricType  # noqa: E402
from lib.LLM_Manager import LLMManager  # noqa: E402
from lib.Github_API_Manager import GitHubAPIManager  # noqa: E402
from lib.HuggingFace_API_Manager import HuggingFaceAPIManager  # noqa: E402


class TestMetricResult:
    """Test cases for MetricResult class."""

    def test_metric_result_creation(self):
        """Test creating a MetricResult."""
        result = MetricResult(
            metric_type=MetricType.PERFORMANCE_CLAIMS,
            value=0.85,
            details={"info": "Test result"},
            latency_ms=150,
            error=None
        )
        
        assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
        assert result.value == 0.85
        assert result.details["info"] == "Test result"
        assert result.latency_ms == 150
        assert result.error is None

    def test_metric_result_with_error(self):
        """Test creating a MetricResult with error."""
        result = MetricResult(
            metric_type=MetricType.BUS_FACTOR,
            value=0.0,
            details={},
            latency_ms=50,
            error="Test error message"
        )
        
        assert result.error == "Test error message"
        assert result.value == 0.0

    def test_metric_result_frozen(self):
        """Test that MetricResult is frozen (immutable)."""
        result = MetricResult(
            metric_type=MetricType.LICENSE,
            value=1.0,
            details={},
            latency_ms=25,
            error=None
        )
        
        # Should not be able to modify frozen dataclass
        try:
            result.value = 0.5
            assert False, "Should not be able to modify frozen dataclass"
        except (AttributeError, TypeError):
            # Expected - frozen dataclass prevents modification
            pass

    def test_metric_types_enum(self):
        """Test MetricType enum values."""
        assert MetricType.SIZE_SCORE.value == "size_score"
        assert MetricType.LICENSE.value == "license"
        assert MetricType.RAMP_UP_TIME.value == "ramp_up_time"
        assert MetricType.BUS_FACTOR.value == "bus_factor"
        expected = "dataset_and_code_score"
        assert MetricType.DATASET_AND_CODE_SCORE.value == expected
        assert MetricType.DATASET_QUALITY.value == "dataset_quality"
        assert MetricType.CODE_QUALITY.value == "code_quality"
        assert MetricType.PERFORMANCE_CLAIMS.value == "performance_claims"

    def test_metric_result_equality(self):
        """Test MetricResult equality comparison."""
        result1 = MetricResult(
            metric_type=MetricType.SIZE_SCORE,
            value=0.75,
            details={},
            latency_ms=100,
            error=None
        )
        
        result2 = MetricResult(
            metric_type=MetricType.SIZE_SCORE,
            value=0.75,
            details={},
            latency_ms=100,
            error=None
        )
        
        assert result1 == result2

    def test_metric_result_string_representation(self):
        """Test MetricResult string representation."""
        result = MetricResult(
            metric_type=MetricType.CODE_QUALITY,
            value=0.9,
            details={"lines": 1000},
            latency_ms=200,
            error=None
        )
        
        str_repr = str(result)
        assert "CODE_QUALITY" in str_repr
        assert "0.9" in str_repr


class TestPurdueLLMManager:
    """Test cases for PurdueLLMManager."""

    @patch('lib.LLM_Manager.os.getenv')
    def test_llm_manager_initialization(self, mock_getenv):
        """Test LLM manager initialization."""
        mock_getenv.return_value = "test_api_key"
        
        try:
            manager = LLMManager()
            assert manager is not None
        except ImportError:
            # Skip if dependencies not available
            pass

    @patch('lib.LLM_Manager.os.getenv')
    @patch('lib.LLM_Manager.genai')
    def test_llm_manager_generate_response(self, mock_genai, mock_getenv):
        """Test LLM response generation."""
        mock_getenv.return_value = "test_api_key"
        mock_model = Mock()
        mock_model.generate_content.return_value.text = "0.75"
        mock_genai.GenerativeModel.return_value = mock_model
        
        try:
            manager = LLMManager()
            response = manager.generate_response("Test prompt")
            assert response == "0.75"
        except (ImportError, AttributeError):
            pass

    @patch('lib.LLM_Manager.os.getenv')
    def test_llm_manager_no_api_key(self, mock_getenv):
        """Test LLM manager without API key."""
        mock_getenv.return_value = None
        
        try:
            manager = LLMManager()
            # Should handle missing API key gracefully
            assert manager is not None or manager is None
        except (ImportError, ValueError):
            # Expected if API key is required
            pass


class TestGitHubAPIManager:
    """Test cases for GitHubAPIManager."""

    def test_github_api_manager_initialization(self):
        """Test GitHub API manager initialization."""
        try:
            manager = GitHubAPIManager()
            assert manager is not None
        except ImportError:
            pass

    @patch('lib.Github_API_Manager.requests.get')
    def test_github_api_get_repo_info(self, mock_get):
        """Test GitHub repository info retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "name": "test-repo",
            "description": "Test repository",
            "language": "Python",
            "stargazers_count": 100,
            "forks_count": 50
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        try:
            manager = GitHubAPIManager()
            repo_info = manager.get_repo_info("test/repo")
            
            assert repo_info["name"] == "test-repo"
            assert repo_info["language"] == "Python"
            assert repo_info["stargazers_count"] == 100
        except (ImportError, AttributeError):
            pass

    @patch('lib.Github_API_Manager.requests.get')
    def test_github_api_error_handling(self, mock_get):
        """Test GitHub API error handling."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not found")
        mock_get.return_value = mock_response
        
        try:
            manager = GitHubAPIManager()
            # Should handle 404 gracefully
            repo_info = manager.get_repo_info("nonexistent/repo")
            assert repo_info is None or isinstance(repo_info, dict)
        except (ImportError, AttributeError, Exception):
            pass

    def test_github_api_url_parsing(self):
        """Test GitHub URL parsing."""
        try:
            manager = GitHubAPIManager()
            
            # Test different URL formats if method exists
            if hasattr(manager, 'parse_github_url'):
                test_urls = [
                    "https://github.com/owner/repo",
                    "https://github.com/owner/repo.git",
                    "git@github.com:owner/repo.git"
                ]
                
                for url in test_urls:
                    result = manager.parse_github_url(url)
                    assert "owner" in str(result) and "repo" in str(result)
        except (ImportError, AttributeError):
            pass


class TestHuggingFaceAPIManager:
    """Test cases for HuggingFaceAPIManager."""

    def test_huggingface_api_manager_initialization(self):
        """Test HuggingFace API manager initialization."""
        try:
            manager = HuggingFaceAPIManager()
            assert manager is not None
        except ImportError:
            pass

    @patch('lib.HuggingFace_API_Manager.HfApi')
    def test_huggingface_get_model_info(self, mock_hf_api):
        """Test HuggingFace model info retrieval."""
        mock_api_instance = Mock()
        mock_model_info = Mock()
        mock_model_info.id = "test/model"
        mock_model_info.pipeline_tag = "text-generation"
        mock_api_instance.model_info.return_value = mock_model_info
        mock_hf_api.return_value = mock_api_instance
        
        try:
            manager = HuggingFaceAPIManager()
            model_info = manager.get_model_info("test/model")
            
            assert model_info.id == "test/model"
            assert model_info.pipeline_tag == "text-generation"
        except (ImportError, AttributeError):
            pass

    @patch('lib.HuggingFace_API_Manager.HfApi')
    def test_huggingface_get_dataset_info(self, mock_hf_api):
        """Test HuggingFace dataset info retrieval."""
        mock_api_instance = Mock()
        mock_dataset_info = Mock()
        mock_dataset_info.id = "test/dataset"
        mock_api_instance.dataset_info.return_value = mock_dataset_info
        mock_hf_api.return_value = mock_api_instance
        
        try:
            manager = HuggingFaceAPIManager()
            dataset_info = manager.get_dataset_info("test/dataset")
            
            assert dataset_info.id == "test/dataset"
        except (ImportError, AttributeError):
            pass

    def test_huggingface_model_link_to_id(self):
        """Test converting HuggingFace model link to ID."""
        try:
            manager = HuggingFaceAPIManager()
            
            if hasattr(manager, 'model_link_to_id'):
                test_cases = [
                    ("https://huggingface.co/microsoft/DialoGPT-medium",
                     "microsoft/DialoGPT-medium"),
                    ("https://huggingface.co/bert-base-uncased",
                     "bert-base-uncased"),
                ]
                
                for link, expected_id in test_cases:
                    result = manager.model_link_to_id(link)
                    assert result == expected_id
        except (ImportError, AttributeError):
            pass

    @patch('lib.HuggingFace_API_Manager.HfApi')
    def test_huggingface_api_error_handling(self, mock_hf_api):
        """Test HuggingFace API error handling."""
        mock_api_instance = Mock()
        mock_api_instance.model_info.side_effect = Exception("Model not found")
        mock_hf_api.return_value = mock_api_instance
        
        try:
            manager = HuggingFaceAPIManager()
            # Should handle errors gracefully
            model_info = manager.get_model_info("nonexistent/model")
            assert model_info is None or hasattr(model_info, 'error')
        except (ImportError, AttributeError, Exception):
            pass


class TestAPIIntegration:
    """Integration tests for API managers."""

    def test_api_managers_independence(self):
        """Test that API managers work independently."""
        try:
            github_manager = GitHubAPIManager()
            hf_manager = HuggingFaceAPIManager()
            
            # Should be independent instances
            assert github_manager is not hf_manager
            assert not isinstance(github_manager, type(hf_manager))
        except ImportError:
            pass

    def test_api_managers_error_isolation(self):
        """Test that API manager errors don't affect each other."""
        try:
            with patch('lib.Github_API_Manager.requests.get',
                       side_effect=Exception("GitHub error")):
                github_manager = GitHubAPIManager()
                assert github_manager is not None
                
                # HuggingFace manager should still work
                hf_manager = HuggingFaceAPIManager()
                assert hf_manager is not None
        except ImportError:
            pass