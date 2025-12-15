"""
Boost coverage for main.py application logic.
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import main 

class TestMainApplicationCoverage:

    def test_extract_model_name_edge_cases(self):
        """Test extract_model_name with various edge cases."""
        test_cases = [
            ("https://huggingface.co/microsoft/DialoGPT-medium", "DialoGPT-medium"),
            ("https://huggingface.co/openai/gpt-3.5-turbo", "gpt-3.5-turbo"),
            ("https://huggingface.co/xlangai/OpenCUA-32B?tab=model-index", "OpenCUA-32B"),
            # Corrected: generic names without owner return unknown_model
            ("https://huggingface.co/bert-base-uncased", "unknown_model"), 
            ("not-a-url", "unknown_model"),
        ]

        for url, expected in test_cases:
            result = main.extract_model_name(url)
            assert result == expected

    @patch('lib.HuggingFace_API_Manager.HuggingFaceAPIManager')
    def test_find_missing_links_with_readme_file(self, mock_hf_manager):
        mock_mgr = Mock()
        mock_hf_manager.return_value = mock_mgr
        mock_mgr.model_link_to_id.return_value = "test/model"
        
        mock_mgr.get_model_info.return_value = Mock(
            cardData="Dataset: https://huggingface.co/datasets/test/data", 
            tags=[], 
            modelId="test/model"
        )
        
        d_links, c_link = main.find_missing_links("https://huggingface.co/test/model", None, None)
        assert any("datasets/test/data" in d for d in d_links)

    @patch('main.ThreadPoolExecutor')
    @patch('main.ModelMetricService')
    def test_run_evaluations_parallel_execution(self, mock_service_class, mock_executor_class):
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        mock_res = Mock(value=0.5)
        for attr in dir(mock_service):
            if attr.startswith('Evaluate'):
                setattr(mock_service, attr, Mock(return_value=mock_res))
        mock_service.EvaluateReproducibility.return_value = mock_res

        mock_executor = Mock()
        mock_executor_class.return_value.__enter__ = Mock(return_value=mock_executor)
        mock_executor_class.return_value.__exit__ = Mock(return_value=None)

        future = Mock()
        future.result.return_value = (Mock(value=0.5), 0.1)
        
        # Infinite iterator to prevent StopIteration
        import itertools
        mock_executor.submit.side_effect = itertools.repeat(future)
        
        with patch('main.as_completed', return_value=[future] * 9):
            results = main.run_evaluations_parallel(Mock())
            assert isinstance(results, dict)