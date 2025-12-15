"""
Simple coverage tests for Services.
"""
import sys
import os
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType

class TestServicesCoverage:
    
    def setup_method(self):
        # Patch globally
        with patch('lib.LLM_Manager.LLMManager'):
            self.service = ModelMetricService()
    
    def test_service_initialization(self):
        assert self.service is not None
    
    def test_evaluate_performance_claims_empty_model(self):
        mock_model = Mock(spec=Model)
        mock_model.card = ""
        mock_model.readme_path = None
        
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"score": 0.0}')
            result = self.service.EvaluatePerformanceClaims(mock_model)
            assert result.value == 0.0
    
    def test_evaluate_bus_factor_no_contributors(self):
        mock_model = Mock(spec=Model)
        mock_model.code_link = None
        mock_model.repo_contributors = []
        mock_model.repo_commit_history = []
        
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.value == 0.15 # Base score
    
    def test_evaluate_size_no_model_file(self):
        mock_model = Mock(spec=Model)
        mock_model.model_file_size = None
        mock_model.repo_metadata = {}
        
        result = self.service.EvaluateSize(mock_model)
        # Your logic: 0 size -> band <= 200MB -> score 1.0
        assert result.value == 1.0
    
    def test_evaluate_size_with_size(self):
        mock_model = Mock(spec=Model)
        mock_model.model_file_size = None
        # Use integer or float to avoid parsing error in your code
        mock_model.repo_metadata = {"size": 500} # 500MB
        
        result = self.service.EvaluateSize(mock_model)
        assert result.value > 0
    
    def test_evaluate_ramp_up_time_no_readme(self):
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        mock_model.card = ""
        
        result = self.service.EvaluateRampUpTime(mock_model)
        assert result.value == 0.0
    
    def test_evaluate_ramp_up_time_with_readme(self):
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        mock_model.card = "Docs"
        
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"quality_of_example_code": 0.8, "readme_coverage": 0.8}')
            result = self.service.EvaluateRampUpTime(mock_model)
            assert result.value == 0.8
    
    def test_evaluate_license_no_license(self):
        mock_model = Mock(spec=Model)
        mock_model.license = None
        mock_model.readme_path = None
        mock_model.repo_metadata = {}
        mock_model.card = {}
        
        result = self.service.EvaluateLicense(mock_model)
        assert result.value == 0.0
    
    def test_evaluate_license_with_license(self):
        mock_model = Mock(spec=Model)
        # Your service checks card/repo_metadata, NOT model.license directly
        mock_model.card = {"license": "MIT"}
        mock_model.repo_metadata = {}
        mock_model.readme_path = None
        
        result = self.service.EvaluateLicense(mock_model)
        assert result.value == 1.0
    
    def test_evaluate_code_quality_no_code(self):
        mock_model = Mock(spec=Model)
        mock_model.code_link = None
        mock_model.repo_contents = []
        
        result = self.service.EvaluateCodeQuality(mock_model)
        assert result.value == 0.5
    
    def test_evaluate_datasets_quality_no_datasets(self):
        mock_model = Mock(spec=Model)
        mock_model.dataset_links = []
        mock_model.dataset_cards = {}
        mock_model.dataset_infos = {}
        
        result = self.service.EvaluateDatasetsQuality(mock_model)
        assert result.value == 0.5