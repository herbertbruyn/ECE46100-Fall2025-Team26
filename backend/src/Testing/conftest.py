"""
Conftest file for pytest configuration and fixtures.
Contains shared fixtures and test setup for the ML Model Evaluation System.
"""
import pytest
import os
import sys
from unittest.mock import Mock, MagicMock
from datetime import datetime

# Add backend/src to Python path for imports
backend_src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)))
if backend_src_path not in sys.path:
    sys.path.insert(0, backend_src_path)

# Import after adding to path
from lib.Metric_Result import MetricResult, MetricType  # noqa: E402
from Models.Model import Model  # noqa: E402


@pytest.fixture
def mock_model():
    """Create a mock Model instance for testing."""
    model = Mock(spec=Model)
    model.model_link = "https://huggingface.co/test/model"
    model.dataset_links = ["https://huggingface.co/datasets/test/dataset"]
    model.code_link = "https://github.com/test/repo"
    model.readme_path = None
    model.card = None
    model.model_description = "Test model description"
    model.dataset_descriptions = ["Test dataset description"]
    model.code_description = "Test code description"
    return model


@pytest.fixture
def sample_metric_result():
    """Create a sample MetricResult for testing."""
    return MetricResult(
        metric_type=MetricType.PERFORMANCE_CLAIMS,
        value=0.75,
        details={"info": "Test metric result"},
        latency_ms=100,
        error=None
    )


@pytest.fixture
def mock_llm_manager():
    """Create a mock LLM Manager for testing."""
    manager = MagicMock()
    manager.generate_response.return_value = "Test response"
    return manager


@pytest.fixture
def mock_github_api():
    """Create a mock GitHub API manager for testing."""
    api = MagicMock()
    api.get_repo_info.return_value = {
        "name": "test-repo",
        "description": "Test repository",
        "language": "Python",
        "stars": 100,
        "forks": 50
    }
    return api


@pytest.fixture
def mock_huggingface_api():
    """Create a mock HuggingFace API manager for testing."""
    api = MagicMock()
    api.get_model_info.return_value = MagicMock()
    api.get_dataset_info.return_value = MagicMock()
    return api


@pytest.fixture
def temp_readme_file(tmp_path):
    """Create a temporary README file for testing."""
    readme_content = """
    # Test Model
    
    This is a test model for evaluation.
    
    ## Performance
    - Accuracy: 95%
    - F1 Score: 0.92
    
    ## License
    MIT License
    """
    readme_file = tmp_path / "README.md"
    readme_file.write_text(readme_content)
    return str(readme_file)


@pytest.fixture
def sample_urls():
    """Sample URLs for testing input parsing."""
    return [
        ("https://github.com/test/repo1,https://huggingface.co/datasets/"
         "test/dataset1,https://huggingface.co/test/model1"),
        "https://github.com/test/repo2,,https://huggingface.co/test/model2",
        ",,https://huggingface.co/test/model3"
    ]


@pytest.fixture
def mock_datetime():
    """Mock datetime for consistent testing."""
    return datetime(2025, 1, 1, 12, 0, 0)


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Setup test environment variables."""
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("HUGGINGFACE_TOKEN", "test_token")
    monkeypatch.setenv("GOOGLE_AI_API_KEY", "test_key")
    monkeypatch.setenv("GEN_AI_STUDIO_API_KEY", "test_api_key")
    monkeypatch.setenv("GEMINI_API_KEY", "test_gemini_key")