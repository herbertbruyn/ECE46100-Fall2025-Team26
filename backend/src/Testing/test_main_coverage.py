"""
Additional test cases for main.py to increase coverage.
"""
import pytest
import sys
import os
from unittest.mock import Mock, patch, mock_open, MagicMock
from Models.Model import Model

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import main


class TestMainCoverageFunctions:
    """Test functions in main.py to boost coverage."""
    
    def test_time_evaluation_success(self):
        """Test timing a successful evaluation."""
        def dummy_eval(*args, **kwargs):
            return Mock(metric_type="TEST", value=0.5)
        
        result, execution_time = main.time_evaluation(dummy_eval, "arg1", kwarg1="test")
        
        assert result is not None
        assert execution_time >= 0
        assert result.metric_type == "TEST"
        assert result.value == 0.5
    
    def test_time_evaluation_exception(self):
        """Test timing an evaluation that raises an exception."""
        def failing_eval(*args, **kwargs):
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            main.time_evaluation(failing_eval, "arg1")
    
    @patch('main.ModelMetricService')
    def test_run_evaluations_sequential(self, mock_service_class):
        """Test sequential evaluation runner."""
        # Mock service instance
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        # Mock evaluation methods
        mock_service.EvaluatePerformanceClaimsScore.return_value = Mock(metric_type="PERF", value=0.8)
        mock_service.EvaluateBusFactorScore.return_value = Mock(metric_type="BUS", value=0.6)
        mock_service.EvaluateSizeScore.return_value = Mock(metric_type="SIZE", value=0.4)
        mock_service.EvaluateRampUpTimeScore.return_value = Mock(metric_type="RAMP", value=0.3)
        mock_service.EvaluateDatasetAndCodeAvailabilityScore.return_value = Mock(metric_type="AVAIL", value=0.2)
        mock_service.EvaluateCodeQualityScore.return_value = Mock(metric_type="CODE", value=0.7)
        mock_service.EvaluateDatasetsQualityScore.return_value = Mock(metric_type="DATA", value=0.5)
        mock_service.EvaluateLicenseScore.return_value = Mock(metric_type="LICENSE", value=0.9)
        
        # Mock model data
        mock_model = Mock()
        
        # Call the function
        results = main.run_evaluations_sequential(mock_model)
        
        # Verify results
        assert len(results) == 8
        assert "Performance Claims" in results
        assert "Bus Factor" in results
        assert "Size" in results
        assert "Ramp Up Time" in results
        assert "Dataset and Code Availability" in results
        assert "Code Quality" in results
        assert "Datasets Quality" in results
        assert "License" in results
        
        # Check that each result is a tuple of (MetricResult, float)
        for key, (result, time_taken) in results.items():
            assert hasattr(result, 'metric_type')
            assert isinstance(time_taken, float)
            assert time_taken >= 0
    
    @patch('main.ModelMetricService')
    @patch('main.ThreadPoolExecutor')
    def test_run_evaluations_parallel(self, mock_executor_class, mock_service_class):
        """Test parallel evaluation runner."""
        # Mock service
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        # Mock executor
        mock_executor = Mock()
        mock_executor_class.return_value.__enter__ = Mock(return_value=mock_executor)
        mock_executor_class.return_value.__exit__ = Mock(return_value=None)
        
        # Mock future objects
        mock_futures = []
        for i in range(8):
            future = Mock()
            future.result.return_value = (Mock(metric_type=f"TEST{i}", value=0.5), 0.1)
            mock_futures.append(future)
        
        mock_executor.submit.side_effect = mock_futures
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=None)
        
        # Mock as_completed
        with patch('main.as_completed', return_value=mock_futures):
            # Mock model data
            mock_model = Mock()
            
            # Call the function
            results = main.run_evaluations_parallel(mock_model)
            
            # Verify results
            assert len(results) == 8
            assert mock_executor.submit.call_count == 8
    
    def test_extract_model_name_valid_urls(self):
        """Test extracting model names from various valid URLs."""
        test_cases = [
            ("https://huggingface.co/microsoft/DialoGPT-medium", "microsoft/DialoGPT-medium"),
            ("https://huggingface.co/bert-base-uncased", "bert-base-uncased"),
            ("https://huggingface.co/openai/gpt-3.5-turbo", "openai/gpt-3.5-turbo"),
        ]
        
        for url, expected in test_cases:
            result = main.extract_model_name(url)
            assert result == expected
    
    def test_extract_model_name_invalid_urls(self):
        """Test extracting model names from invalid URLs returns unknown."""
        test_cases = [
            "not-a-url",
            "https://github.com/some/repo",
            "https://example.com/model",
            "",
            None
        ]
        
        for url in test_cases:
            result = main.extract_model_name(url)
            assert result == "unknown_model"
    
    def test_ndjson_serializer_success(self):
        """Test NDJSON serialization of results."""
        # Mock results
        mock_results = {
            "Model1": {
                "Performance Claims": (Mock(metric_type="PERF", value=0.8), 0.1),
                "Bus Factor": (Mock(metric_type="BUS", value=0.6), 0.2)
            }
        }
        
        # Mock the MetricResult objects to have proper attributes
        for model_results in mock_results.values():
            for metric_name, (result, time_taken) in model_results.items():
                result.to_dict.return_value = {
                    "metric_type": result.metric_type,
                    "value": result.value,
                    "details": {},
                    "latency_ms": 0
                }
        
        # Mock open
        with patch('builtins.open', mock_open()) as mock_file:
            main.ndjson_serializer(mock_results, "test_output.ndjson")
            
            # Verify file was opened for writing
            mock_file.assert_called_once_with("test_output.ndjson", "w", encoding="utf-8")
    
    def test_ndjson_serializer_empty_results(self):
        """Test NDJSON serialization with empty results."""
        with patch('builtins.open', mock_open()) as mock_file:
            main.ndjson_serializer({}, "empty_output.ndjson")
            
            # Verify file was still opened
            mock_file.assert_called_once()
    
    def test_csv_serializer_success(self):
        """Test CSV serialization of results."""
        # Mock results with proper structure
        mock_results = {
            "Model1": {
                "Performance Claims": (Mock(metric_type="PERF", value=0.8), 0.1),
                "Bus Factor": (Mock(metric_type="BUS", value=0.6), 0.2)
            }
        }
        
        # Mock the MetricResult objects
        for model_results in mock_results.values():
            for metric_name, (result, time_taken) in model_results.items():
                result.value = result.value
        
        with patch('builtins.open', mock_open()) as mock_file, \
             patch('csv.writer') as mock_csv_writer:
            
            mock_writer = Mock()
            mock_csv_writer.return_value = mock_writer
            
            main.csv_serializer(mock_results, "test_output.csv")
            
            # Verify file operations
            mock_file.assert_called_once_with("test_output.csv", "w", newline="", encoding="utf-8")
            mock_csv_writer.assert_called_once()
            assert mock_writer.writerow.call_count >= 1  # At least header row
    
    def test_csv_serializer_empty_results(self):
        """Test CSV serialization with empty results."""
        with patch('builtins.open', mock_open()) as mock_file, \
             patch('csv.writer') as mock_csv_writer:
            
            mock_writer = Mock()
            mock_csv_writer.return_value = mock_writer
            
            main.csv_serializer({}, "empty_output.csv")
            
            # Verify operations still occurred
            mock_file.assert_called_once()
            mock_csv_writer.assert_called_once()
    
    @patch('main.Controller')
    def test_find_missing_links_no_missing(self, mock_controller_class):
        """Test find_missing_links when no links are missing."""
        # Mock controller
        mock_controller = Mock()
        mock_controller_class.return_value = mock_controller
        
        # Mock model with all links present
        mock_model = Mock()
        mock_model.dataset_links = ["https://huggingface.co/datasets/test"]
        mock_model.code_link = "https://github.com/test/repo"
        mock_model.card = "Model card content"
        mock_model.readme_path = None
        
        # Call function
        result = main.find_missing_links(mock_model)
        
        # Should return model unchanged if no missing links
        assert result == mock_model
    
    @patch('main.Controller')
    def test_find_missing_links_with_discovery(self, mock_controller_class):
        """Test find_missing_links when links need to be discovered."""
        # Mock controller
        mock_controller = Mock()
        mock_controller_class.return_value = mock_controller
        
        # Mock model with missing links
        mock_model = Mock()
        mock_model.dataset_links = []
        mock_model.code_link = None
        mock_model.card = "Check out the dataset at https://huggingface.co/datasets/found_dataset"
        mock_model.readme_path = None
        
        # Call function
        result = main.find_missing_links(mock_model)
        
        # Should process the model
        assert result is not None