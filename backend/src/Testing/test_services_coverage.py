"""
Simple coverage tests for Services to boost overall coverage.
"""
import sys
import os
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType


class TestServicesCoverage:
    """Simple tests to boost services coverage."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('Services.Metric_Model_Service.LLMManager'):
            self.service = ModelMetricService()
    
    def test_service_initialization(self):
        """Test service can be initialized."""
        with patch('Services.Metric_Model_Service.LLMManager'):
            service = ModelMetricService()
            assert service is not None
    
    def test_evaluate_performance_claims_empty_model(self):
        """Test performance claims evaluation with empty model."""
        mock_model = Mock(spec=Model)
        mock_model.card = ""
        mock_model.readme_path = None
        
        result = self.service.EvaluatePerformanceClaimsScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
        assert isinstance(result.value, float)
        assert 0 <= result.value <= 1
    
    def test_evaluate_performance_claims_with_claims(self):
        """Test performance claims evaluation with claims."""
        mock_model = Mock(spec=Model)
        mock_model.card = ("This model achieves 95% accuracy. "
                           "F1 score is 0.89.")
        mock_model.readme_path = None
        
        result = self.service.EvaluatePerformanceClaimsScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
        assert result.value > 0  # Should find performance claims
    
    def test_evaluate_bus_factor_no_contributors(self):
        """Test bus factor evaluation with no contributors."""
        mock_model = Mock(spec=Model)
        mock_model.code_link = None
        
        result = self.service.EvaluateBusFactorScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.BUS_FACTOR
        assert result.value == 0  # No code link = 0 bus factor
    
    def test_evaluate_size_no_model_file(self):
        """Test size evaluation with no model file."""
        mock_model = Mock(spec=Model)
        mock_model.model_file_size = None
        
        result = self.service.EvaluateSizeScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.SIZE
        assert result.value == 0  # No size info = 0 score
    
    def test_evaluate_size_with_size(self):
        """Test size evaluation with model file size."""
        mock_model = Mock(spec=Model)
        mock_model.model_file_size = 500 * 1024 * 1024  # 500MB
        
        result = self.service.EvaluateSizeScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.SIZE
        assert isinstance(result.value, float)
        assert 0 <= result.value <= 1
    
    def test_evaluate_ramp_up_time_no_readme(self):
        """Test ramp up time evaluation with no README."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        mock_model.card = ""
        
        result = self.service.EvaluateRampUpTimeScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.RAMP_UP_TIME
        assert result.value == 0  # No documentation = 0 score
    
    def test_evaluate_ramp_up_time_with_readme(self):
        """Test ramp up time evaluation with README."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        mock_model.card = """
        # Model Usage
        
        This model can be used as follows:
        
        ```python
        from transformers import AutoModel
        model = AutoModel.from_pretrained("model_name")
        ```
        
        ## Installation
        
        pip install transformers
        
        ## Examples
        
        Here are some examples of how to use this model.
        """
        
        result = self.service.EvaluateRampUpTimeScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.RAMP_UP_TIME
        assert result.value > 0  # Should find documentation
    
    def test_evaluate_license_no_license(self):
        """Test license evaluation with no license."""
        mock_model = Mock(spec=Model)
        mock_model.license = None
        mock_model.readme_path = None
        
        result = self.service.EvaluateLicenseScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.LICENSE
        assert result.value == 0  # No license = 0 score
    
    def test_evaluate_license_with_license(self):
        """Test license evaluation with license."""
        mock_model = Mock(spec=Model)
        mock_model.license = "MIT"
        mock_model.readme_path = None
        
        result = self.service.EvaluateLicenseScore(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.LICENSE
        assert result.value > 0  # Should find license
    
    def test_evaluate_code_quality_no_code(self):
        """Test code quality evaluation with no code link."""
        mock_model = Mock(spec=Model)
        mock_model.code_link = None
        
        # Mock the LLM manager to avoid API calls
        with patch.object(self.service, 'llm_manager') as mock_llm:
            mock_response = Mock()
            mock_response.content = '{"has_tests": false, "has_documentation": false, "code_quality_score": 0}'
            mock_llm.call_genai_api.return_value = mock_response
            
            result = self.service.EvaluateCodeQualityScore(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.CODE_QUALITY
            assert result.value == 0  # No code = 0 score
    
    def test_evaluate_datasets_quality_no_datasets(self):
        """Test datasets quality evaluation with no datasets."""
        mock_model = Mock(spec=Model)
        mock_model.dataset_links = []
        
        # Mock the LLM manager
        with patch.object(self.service, 'llm_manager') as mock_llm:
            mock_response = Mock()
            mock_response.content = '{"datasets_quality_score": 0, "notes": "No datasets found"}'
            mock_llm.call_genai_api.return_value = mock_response
            
            result = self.service.EvaluateDatasetsQualityScore(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.DATASETS_QUALITY
            assert result.value == 0  # No datasets = 0 score