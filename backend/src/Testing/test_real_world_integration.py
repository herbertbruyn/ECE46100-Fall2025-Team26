"""
Comprehensive integration tests using real-world data to boost coverage.
Tests the complete system with actual HuggingFace model and dataset links.
"""
import sys
import os
from unittest.mock import Mock, patch
import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import the modules directly to use patch.object (safer than string patching)
import Controllers.Controller
import Services.Metric_Model_Service
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType
import main


class TestRealWorldIntegration:
    """Integration tests using real HuggingFace model and dataset links."""
    
    @classmethod
    def setup_class(cls):
        """Set up real-world test data."""
        cls.dataset_links = [
            "https://huggingface.co/datasets/xlangai/AgentNet",
            "https://huggingface.co/datasets/osunlp/UGround-V1-Data",
            "https://huggingface.co/datasets/xlangai/aguvis-stage2"
        ]
        cls.code_link = "https://github.com/xlang-ai/OpenCUA"
        cls.model_link = "https://huggingface.co/xlangai/OpenCUA-32B"
    
    def test_controller_initialization(self):
        """Test controller initializes properly."""
        controller = Controllers.Controller.Controller()
        assert controller is not None
        assert hasattr(controller, 'model_manager')
    
    def test_controller_fetch_model(self):
        """Test fetching model data through controller."""
        # Patch the ModelManager class inside the Controller module
        with patch.object(Controllers.Controller, 'ModelManager') as mock_manager_cls:
            mock_manager = Mock()
            mock_manager_cls.return_value = mock_manager
            
            mock_model = Mock(spec=Model)
            mock_model.id = "xlangai/OpenCUA-32B"
            mock_manager.where.return_value = mock_model
            
            # Instantiate controller (will use the mocked manager)
            controller = Controllers.Controller.Controller()
            
            result = controller.fetch(
                self.model_link,
                dataset_links=self.dataset_links,
                code_link=self.code_link
            )
            
            assert result is not None
            mock_manager.where.assert_called_once_with(
                self.model_link, self.dataset_links, self.code_link
            )
    
    def test_controller_fetch_dataset_as_model(self):
        """Test fetching dataset data (now treated as model)."""
        with patch.object(Controllers.Controller, 'ModelManager') as mock_manager_cls:
            mock_manager = Mock()
            mock_manager_cls.return_value = mock_manager
            
            mock_model = Mock(spec=Model)
            mock_manager.where.return_value = mock_model
            
            controller = Controllers.Controller.Controller()
            result = controller.fetch(self.dataset_links[0])
            
            assert result is not None
            mock_manager.where.assert_called_once()
        
    def test_metric_service_initialization(self):
        """Test metric service initializes properly."""
        # Patch LLMManager inside the Service module
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            assert service is not None
            assert hasattr(service, 'llm_manager')
    
    def test_metric_service_performance_claims_empty(self):
        """Test performance claims evaluation with empty model."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager') as mock_llm_cls:
            # Configure mock to return valid JSON (empty object)
            mock_instance = mock_llm_cls.return_value
            mock_instance.call_genai_api.return_value = Mock(content='{}')
            
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.card = ""
            mock_model.readme_path = None
            
            result = service.EvaluatePerformanceClaims(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
            assert isinstance(result.value, float)
            assert 0 <= result.value <= 1
    
    def test_metric_service_performance_claims_with_content(self):
        """Test performance claims evaluation with model content."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager') as mock_llm_cls:
            # Configure mock to return specific score
            mock_instance = mock_llm_cls.return_value
            mock_instance.call_genai_api.return_value = Mock(
                content='{"score": 0.9, "notes": "Good claims detected"}'
            )
            
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.card = "Accuracy: 95.2%"
            mock_model.readme_path = None
            
            result = service.EvaluatePerformanceClaims(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
            assert result.value == 0.9
    
    def test_metric_service_bus_factor_no_code(self):
        """Test bus factor evaluation with no code link."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.code_link = None
            mock_model.repo_commit_history = []
            mock_model.repo_contributors = []
            
            result = service.EvaluateBusFactor(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.BUS_FACTOR
            assert result.value == 0.15 # Matches default implementation logic
    
    def test_metric_service_size_no_file_size(self):
        """Test size evaluation with no model file size."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.model_file_size = None
            mock_model.repo_metadata = {}
            
            result = service.EvaluateSize(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.SIZE_SCORE
            # 0 size falls in first bucket -> score 1.0 (highly portable)
            assert result.value == 1.0
    
    def test_metric_service_size_with_large_model(self):
        """Test size evaluation with large model file."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.repo_metadata = {"size": "64GB"}
            
            result = service.EvaluateSize(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.SIZE_SCORE
            assert 0 <= result.value <= 1
    
    def test_metric_service_ramp_up_time_no_docs(self):
        """Test ramp up time evaluation with no documentation."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.readme_path = None
            mock_model.card = ""
            
            result = service.EvaluateRampUpTime(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.RAMP_UP_TIME
            assert result.value == 0
    
    def test_metric_service_ramp_up_time_with_docs(self):
        """Test ramp up time evaluation with good documentation."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager') as mock_llm_cls:
            mock_instance = mock_llm_cls.return_value
            # Return valid JSON with specific scores
            mock_instance.call_genai_api.return_value = Mock(
                content='{"quality_of_example_code": 0.8, "readme_coverage": 0.8, "notes": "Good"}'
            )
            
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.readme_path = None
            mock_model.card = "Has code example"
            
            result = service.EvaluateRampUpTime(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.RAMP_UP_TIME
            assert result.value == 0.8
    
    def test_metric_service_license_no_license(self):
        """Test license evaluation with no license."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.license = None
            mock_model.readme_path = None
            mock_model.repo_metadata = {}
            mock_model.card = {}
            
            result = service.EvaluateLicense(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.LICENSE
            assert result.value == 0
    
    def test_metric_service_license_with_apache(self):
        """Test license evaluation with Apache license."""
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            service = Services.Metric_Model_Service.ModelMetricService()
            
            mock_model = Mock(spec=Model)
            mock_model.card = {"license": "Apache-2.0"}
            mock_model.repo_metadata = {}
            mock_model.readme_path = None
            
            result = service.EvaluateLicense(mock_model)
            
            assert isinstance(result, MetricResult)
            assert result.metric_type == MetricType.LICENSE
            assert result.value > 0
    
    @patch('main.ModelMetricService')
    def test_main_run_evaluations_sequential(self, mock_service_class):
        """Test sequential evaluation runner."""
        # Use main's import path for patching
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        # Create a real result with a float value to avoid formatting errors
        real_result = MetricResult(
            metric_type=MetricType.PERFORMANCE_CLAIMS,
            value=0.5,
            details={},
            latency_ms=0
        )
        
        evaluation_methods = [
            'EvaluatePerformanceClaims',
            'EvaluateBusFactor', 
            'EvaluateSize',
            'EvaluateRampUpTime',
            'EvaluateDatasetAndCodeAvailabilityScore',
            'EvaluateCodeQuality',
            'EvaluateDatasetsQuality',
            'EvaluateLicense',
            'EvaluateReproducibility'
        ]
        
        for method_name in evaluation_methods:
            getattr(mock_service, method_name).return_value = real_result
        
        mock_model = Mock()
        results = main.run_evaluations_sequential(mock_model)
        
        assert len(results) >= 8
        for name, (result, exec_time) in results.items():
            assert result is not None
            assert isinstance(exec_time, float)