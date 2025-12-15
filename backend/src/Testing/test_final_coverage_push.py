"""
Final push for high coverage.
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType

class TestFinalCoveragePush:
    
    def setup_method(self):
        with patch('lib.LLM_Manager.LLMManager'):
            self.service = ModelMetricService()

    def test_performance_claims_file_read_error(self):
        mock_model = Mock(spec=Model)
        mock_model.readme_path = "/tmp/bad_file.md"
        mock_model.card = "Card content"
        
        with patch('builtins.open', side_effect=IOError("File not found")):
            with patch.object(self.service.llm_manager, 'call_genai_api') as mock_call:
                mock_call.return_value = Mock(content='{"score": 0.5}')
                result = self.service.EvaluatePerformanceClaims(mock_model)
                assert result.value == 0.5

    def test_error_handling_paths(self):
        """Cover general exception blocks."""
        mock_model = Mock(spec=Model)
        # Setting this to None causes TypeError when iterated, triggering exception handler
        mock_model.repo_commit_history = None
        mock_model.repo_contributors = []
        
        with pytest.raises(RuntimeError):
            self.service.EvaluateBusFactor(mock_model)