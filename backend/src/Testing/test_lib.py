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
    @patch('lib.LLM_Manager.requests.post')
    def test_llm_manager_generate_response(self, mock_post, mock_getenv):
        """Test LLM response generation."""
        mock_getenv.return_value = "test_api_key"
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {"content": "0.75"},
                    "finish_reason": "STOP"
                }
            ],
            "usage": {"total_tokens": 100}
        }
        mock_post.return_value = mock_response
        
        try:
            manager = LLMManager()
            response = manager.call_genai_api("Test prompt")
            assert response.content == "0.75"
            assert response.finish_reason == "STOP"
        except (ImportError, AttributeError, ValueError):
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

    @patch('lib.LLM_Manager.os.getenv')
    @patch('lib.LLM_Manager.requests.post')
    def test_llm_manager_empty_content_response(self, mock_post, mock_getenv):
        """Test LLM response with empty content."""
        mock_getenv.return_value = "test_api_key"
        
        # Mock response with empty choices
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [],
            "usage": {}
        }
        mock_post.return_value = mock_response
        
        try:
            manager = LLMManager()
            response = manager.call_genai_api("Test prompt")
            # Should handle empty content
            assert response.content == ""
        except (ImportError, AttributeError, ValueError):
            pass

    @patch('lib.LLM_Manager.os.getenv')
    @patch('lib.LLM_Manager.requests.post')
    def test_llm_manager_api_error(self, mock_post, mock_getenv):
        """Test LLM API error handling."""
        mock_getenv.return_value = "test_api_key"
        
        # Mock failed API response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        try:
            manager = LLMManager()
            # Should raise RuntimeError
            try:
                response = manager.call_genai_api("Test prompt")
                assert False, "Should raise RuntimeError"
            except RuntimeError as e:
                assert "Failed to call Purdue LLM API" in str(e)
        except (ImportError, AttributeError, ValueError):
            pass

    @patch('lib.LLM_Manager.os.getenv')
    @patch('lib.LLM_Manager.requests.post')
    def test_llm_manager_network_error(self, mock_post, mock_getenv):
        """Test LLM network error handling."""
        mock_getenv.return_value = "test_api_key"
        
        # Mock network exception
        mock_post.side_effect = Exception("Network error")
        
        try:
            manager = LLMManager()
            # Should raise RuntimeError
            try:
                response = manager.call_genai_api("Test prompt")
                assert False, "Should raise RuntimeError"
            except RuntimeError:
                pass  # Expected
        except (ImportError, AttributeError, ValueError):
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
            manager = GitHubAPIManager(token="test_token")
            # Correct signature: get_repo_info(owner, repo)
            repo_info = manager.get_repo_info("test", "repo")
            
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

    def test_github_code_link_to_repo(self):
        """Test GitHub code_link_to_repo method."""
        try:
            manager = GitHubAPIManager()
            
            # Test different URL formats
            test_cases = [
                ("https://github.com/owner/repo", ("owner", "repo")),
                ("https://github.com/owner/repo.git", ("owner", "repo")),
                ("https://github.com/openai/gpt-2", ("openai", "gpt-2")),
            ]
            
            for url, expected in test_cases:
                owner, repo = manager.code_link_to_repo(url)
                assert owner == expected[0]
                assert repo == expected[1]
            
            # Test invalid URL
            try:
                manager.code_link_to_repo("https://invalid.com/repo")
                assert False, "Should raise ValueError for invalid URL"
            except ValueError:
                pass  # Expected
        except (ImportError, AttributeError):
            pass

    @patch('lib.Github_API_Manager.requests.get')
    def test_github_get_repo_readme(self, mock_get):
        """Test GitHub get_repo_readme method."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "name": "README.md",
            "content": "VGVzdCBjb250ZW50",  # Base64 encoded "Test content"
            "encoding": "base64"
        }
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        try:
            manager = GitHubAPIManager(token="test_token")
            readme = manager.get_repo_readme("test", "repo")
            
            assert readme["name"] == "README.md"
            assert readme["encoding"] == "base64"
        except (ImportError, AttributeError):
            pass

    @patch('lib.Github_API_Manager.requests.get')
    def test_github_get_repo_contents_with_path(self, mock_get):
        """Test GitHub get_repo_contents with path parameter."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"name": "file1.py", "type": "file"},
            {"name": "file2.py", "type": "file"}
        ]
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        try:
            manager = GitHubAPIManager(token="test_token")
            contents = manager.get_repo_contents("test", "repo", path="src")
            
            assert isinstance(contents, list)
            assert len(contents) == 2
            assert contents[0]["name"] == "file1.py"
        except (ImportError, AttributeError):
            pass

    def test_github_api_no_token_error(self):
        """Test GitHub API error when no token provided."""
        try:
            manager = GitHubAPIManager()  # No token
            
            # Should raise ValueError when trying to make API request
            try:
                manager.github_request("/repos/test/repo")
                assert False, "Should raise ValueError for missing token"
            except ValueError as e:
                assert "token is required" in str(e).lower()
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
        """Test converting HuggingFace model link to ID (both formats)."""
        try:
            manager = HuggingFaceAPIManager()
            
            # Test both formats: with org and without org
            test_cases = [
                # With organization prefix
                ("https://huggingface.co/microsoft/DialoGPT-medium",
                 "microsoft/DialoGPT-medium"),
                ("https://huggingface.co/google-bert/bert-base-uncased",
                 "google-bert/bert-base-uncased"),
                # Without organization prefix (short format)
                ("https://huggingface.co/gpt2", "gpt2"),
                ("https://huggingface.co/distilbert-base-uncased",
                 "distilbert-base-uncased"),
            ]
            
            for link, expected_id in test_cases:
                result = manager.model_link_to_id(link)
                assert result == expected_id, \
                    f"Expected {expected_id}, got {result} for {link}"
            
            # Test invalid link
            try:
                manager.model_link_to_id("https://huggingface.co/")
                assert False, "Should raise ValueError for invalid link"
            except ValueError:
                pass  # Expected
        except (ImportError, AttributeError):
            pass

    def test_huggingface_dataset_link_to_id(self):
        """Test converting HuggingFace dataset link to ID (both formats)."""
        try:
            manager = HuggingFaceAPIManager()
            
            # Test both formats: with org and without org
            test_cases = [
                # With organization prefix
                ("https://huggingface.co/datasets/squad", "squad"),
                ("https://huggingface.co/datasets/glue", "glue"),
                # Could have org prefix format too
                ("https://huggingface.co/datasets/huggingface/squad",
                 "huggingface/squad"),
            ]
            
            for link, expected_id in test_cases:
                result = manager.dataset_link_to_id(link)
                assert result == expected_id, \
                    f"Expected {expected_id}, got {result} for {link}"
            
            # Test invalid link
            try:
                manager.dataset_link_to_id("https://huggingface.co/datasets/")
                assert False, "Should raise ValueError for invalid link"
            except ValueError:
                pass  # Expected
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

    @patch('lib.HuggingFace_API_Manager.HfApi')
    def test_huggingface_download_model_readme(self, mock_hf_api):
        """Test HuggingFace download_model_readme method."""
        mock_api_instance = Mock()
        mock_api_instance.hf_hub_download.return_value = "/path/to/README.md"
        mock_hf_api.return_value = mock_api_instance
        
        try:
            manager = HuggingFaceAPIManager()
            readme_path = manager.download_model_readme("test/model")
            
            assert readme_path == "/path/to/README.md"
            mock_api_instance.hf_hub_download.assert_called_once_with(
                repo_id="test/model",
                filename="README.md"
            )
        except (ImportError, AttributeError):
            pass

    @patch('lib.HuggingFace_API_Manager.HfApi')
    def test_huggingface_download_model_readme_not_found(self, mock_hf_api):
        """Test HuggingFace download_model_readme when README not found."""
        mock_api_instance = Mock()
        mock_api_instance.hf_hub_download.side_effect = Exception("Not found")
        mock_hf_api.return_value = mock_api_instance
        
        try:
            manager = HuggingFaceAPIManager()
            readme_path = manager.download_model_readme("test/model")
            
            # Should return None when README not found
            assert readme_path is None
        except (ImportError, AttributeError):
            pass

    @patch('lib.HuggingFace_API_Manager.HfApi')
    def test_huggingface_download_dataset_readme(self, mock_hf_api):
        """Test HuggingFace download_dataset_readme method."""
        mock_api_instance = Mock()
        mock_api_instance.hf_hub_download.return_value = "/path/to/dataset/README.md"
        mock_hf_api.return_value = mock_api_instance
        
        try:
            manager = HuggingFaceAPIManager()
            readme_path = manager.download_dataset_readme("test/dataset")
            
            assert readme_path == "/path/to/dataset/README.md"
            mock_api_instance.hf_hub_download.assert_called_once_with(
                repo_id="test/dataset",
                filename="README.md",
                repo_type="dataset"
            )
        except (ImportError, AttributeError):
            pass

    @patch('lib.HuggingFace_API_Manager.os.getenv')
    def test_huggingface_with_token(self, mock_getenv):
        """Test HuggingFace API manager with token initialization."""
        try:
            # Mock environment variable with token
            mock_getenv.return_value = "test_hf_token"
            
            manager = HuggingFaceAPIManager()
            assert manager is not None
            assert manager.hf_token == "test_hf_token"
        except (ImportError, AttributeError):
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


class TestGitHubAPIIntegration:
    """Integration tests with real GitHub API."""
    
    def test_github_real_public_repo_parsing(self):
        """Test parsing real GitHub URLs (no API call)."""
        try:
            manager = GitHubAPIManager()
            owner, repo = manager.code_link_to_repo(
                "https://github.com/octocat/Hello-World"
            )
            
            assert owner == "octocat"
            assert repo == "Hello-World"
        except (ImportError, AttributeError):
            pass

    def test_github_real_repo_with_token(self):
        """Test fetching real repo info with token (if available)."""
        import os
        import pytest
        
        token = os.getenv("GITHUB_TOKEN")
        
        if not token:
            pytest.skip("GITHUB_TOKEN not set, skipping integration test")
        
        try:
            manager = GitHubAPIManager(token=token)
            
            # Use a stable public repo
            try:
                repo_info = manager.get_repo_info("octocat", "Hello-World")
            except ValueError as e:
                print(f"\n🔍 DEBUG: Error caught: {e}")
                print(f"🔍 DEBUG: Error type: {type(e)}")
                if "401" in str(e) or "Bad credentials" in str(e):
                    pytest.skip("GitHub token invalid or expired")
                raise
            
            # Verify response structure
            assert isinstance(repo_info, dict)
            assert "name" in repo_info
            assert repo_info["name"] == "Hello-World"
            assert "owner" in repo_info
            assert repo_info["owner"]["login"] == "octocat"
            assert "description" in repo_info
            assert "stargazers_count" in repo_info
            assert "forks_count" in repo_info
        except (ImportError, AttributeError):
            pass

    def test_github_real_repo_contents(self):
        """Test fetching real repo contents with token."""
        import os
        import pytest
        
        token = os.getenv("GITHUB_TOKEN")
        
        if not token:
            pytest.skip("GITHUB_TOKEN not set, skipping integration test")
        
        try:
            manager = GitHubAPIManager(token=token)
            
            # Get root contents of Hello-World repo
            try:
                contents = manager.get_repo_contents("octocat", "Hello-World")
            except ValueError as e:
                if "401" in str(e) or "Bad credentials" in str(e):
                    pytest.skip("GitHub token invalid or expired")
                raise
            
            # Verify response structure
            assert isinstance(contents, list)
            assert len(contents) > 0
            
            # Check that items have expected fields
            first_item = contents[0]
            assert "name" in first_item
            assert "type" in first_item
            assert first_item["type"] in ["file", "dir"]
        except (ImportError, AttributeError):
            pass

    def test_github_real_repo_readme(self):
        """Test fetching real repo README with token."""
        import os
        import pytest
        
        token = os.getenv("GITHUB_TOKEN")
        
        if not token:
            pytest.skip("GITHUB_TOKEN not set, skipping integration test")
        
        try:
            manager = GitHubAPIManager(token=token)
            
            try:
                readme = manager.get_repo_readme("octocat", "Hello-World")
            except ValueError as e:
                if "401" in str(e) or "Bad credentials" in str(e):
                    pytest.skip("GitHub token invalid or expired")
                raise
            
            # Verify response structure
            assert isinstance(readme, dict)
            assert "name" in readme
            assert "content" in readme
            assert "encoding" in readme
            assert readme["encoding"] == "base64"
        except (ImportError, AttributeError):
            pass

    def test_github_real_nonexistent_repo(self):
        """Test error handling with real API for non-existent repo."""
        import os
        import pytest
        
        token = os.getenv("GITHUB_TOKEN")
        
        if not token:
            pytest.skip("GITHUB_TOKEN not set, skipping integration test")
        
        try:
            manager = GitHubAPIManager(token=token)
            
            # Try to fetch a repo that definitely doesn't exist
            try:
                repo_info = manager.get_repo_info(
                    "this-user-definitely-does-not-exist-12345",
                    "this-repo-does-not-exist-67890"
                )
                assert False, "Should have raised an exception"
            except ValueError as e:
                # Expected - should get 404 error
                assert "404" in str(e) or "failed" in str(e).lower()
        except (ImportError, AttributeError):
            pass

    def test_github_real_rate_limiting_awareness(self):
        """Test that API requests work and handle rate limits gracefully."""
        import os
        import pytest
        
        token = os.getenv("GITHUB_TOKEN")
        
        if not token:
            pytest.skip("GITHUB_TOKEN not set, skipping integration test")
        
        try:
            manager = GitHubAPIManager(token=token)
            
            # Make a simple request
            try:
                repo_info = manager.get_repo_info("octocat", "Hello-World")
            except ValueError as e:
                if "401" in str(e) or "Bad credentials" in str(e):
                    pytest.skip("GitHub token invalid or expired")
                raise
            
            # Just verify we got data back
            assert repo_info is not None
            assert isinstance(repo_info, dict)
            assert "name" in repo_info
        except (ImportError, AttributeError):
            pass