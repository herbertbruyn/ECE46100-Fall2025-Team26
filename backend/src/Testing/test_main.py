"""
Unit tests for the main.py module functionality.
Tests input parsing, evaluation timing, and output formatting.
"""
import pytest
import tempfile
import os
import sys
import types
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import after adding to path
from main import (
    parse_input,
    time_evaluation,
    extract_model_name,
    format_size_score,
    run_evaluations_sequential,
    run_evaluations_parallel,
    find_missing_links,
    print_timing_summary
)
import main
from lib.Metric_Result import MetricResult, MetricType


class TestParseInput:
    """Test cases for input file parsing."""

    def test_parse_empty_file(self):
        """Test parsing an empty input file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False,
                                         suffix='.txt') as f:
            f.write("")
            temp_path = f.name

        try:
            result = parse_input(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)

    def test_parse_single_model_link(self):
        """Test parsing file with single model link."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False,
                                         suffix='.txt') as f:
            f.write("https://huggingface.co/test/model")
            temp_path = f.name

        try:
            result = parse_input(temp_path)
            expected = [{
                'model_link': 'https://huggingface.co/test/model',
                'dataset_link': None,
                'code_link': None
            }]
            assert result == expected
        finally:
            os.unlink(temp_path)

    def test_parse_full_csv_line(self):
        """Test parsing CSV line with all three links."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False,
                                         suffix='.txt') as f:
            content = ("https://github.com/test/repo,"
                       "https://huggingface.co/datasets/test/dataset,"
                       "https://huggingface.co/test/model")
            f.write(content)
            temp_path = f.name

        try:
            result = parse_input(temp_path)
            expected = [{
                'model_link': 'https://huggingface.co/test/model',
                'dataset_link': 'https://huggingface.co/datasets/test/dataset',
                'code_link': 'https://github.com/test/repo'
            }]
            assert result == expected
        finally:
            os.unlink(temp_path)


class TestTimeEvaluation:
    """Test cases for evaluation timing functionality."""

    def test_time_evaluation_success(self):
        """Test timing a successful evaluation."""
        def dummy_eval(*args, **kwargs):
            return MetricResult(
                metric_type=MetricType.PERFORMANCE_CLAIMS,
                value=0.8,
                details={},
                latency_ms=100,
                error=None
            )

        result, exec_time = time_evaluation(dummy_eval)
        assert isinstance(result, MetricResult)
        assert result.value == 0.8
        assert exec_time >= 0

    def test_time_evaluation_exception(self):
        """Test timing evaluation that raises exception."""
        def failing_eval():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            time_evaluation(failing_eval)


class TestExtractModelName:
    """Test cases for model name extraction."""

    def test_extract_model_name_standard(self):
        """Test extracting model name from standard HF link."""
        link = "https://huggingface.co/microsoft/DialoGPT-medium"
        result = extract_model_name(link)
        assert result == "DialoGPT-medium"

    def test_extract_model_name_invalid_link(self):
        """Test extracting model name from invalid link."""
        link = "https://example.com/invalid/link"
        result = extract_model_name(link)
        assert result == "unknown_model"


@patch('main.ModelMetricService')
class TestRunEvaluations:
    """Test cases for running evaluations."""

    def test_run_evaluations_sequential(self, mock_service_class):
        """Test running evaluations sequentially."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        # Setup mock evaluations with REAL MetricResult objects (float values)
        mock_result = MetricResult(
            metric_type=MetricType.PERFORMANCE_CLAIMS,
            value=0.7,
            details={},
            latency_ms=100
        )
        
        for method_name in [
            'EvaluatePerformanceClaims', 'EvaluateBusFactor', 'EvaluateSize',
            'EvaluateRampUpTime', 'EvaluateDatasetAndCodeAvailabilityScore',
            'EvaluateCodeQuality', 'EvaluateDatasetsQuality', 'EvaluateLicense',
            'EvaluateReproducibility'
        ]:
            setattr(mock_service, method_name, Mock(return_value=mock_result))
        
        mock_model_data = Mock()
        results = run_evaluations_sequential(mock_model_data)
        
        assert len(results) >= 8
        for name, (result, exec_time) in results.items():
            assert isinstance(result, MetricResult)
            assert exec_time >= 0

    def test_run_evaluations_parallel(self, mock_service_class):
        """Test running evaluations in parallel."""
        mock_service = Mock()
        mock_service_class.return_value = mock_service
        
        mock_result = MetricResult(
            metric_type=MetricType.PERFORMANCE_CLAIMS,
            value=0.7,
            details={},
            latency_ms=100
        )
        
        for method_name in [
            'EvaluatePerformanceClaims', 'EvaluateBusFactor', 'EvaluateSize',
            'EvaluateRampUpTime', 'EvaluateDatasetAndCodeAvailabilityScore',
            'EvaluateCodeQuality', 'EvaluateDatasetsQuality', 'EvaluateLicense',
            'EvaluateReproducibility'
        ]:
            setattr(mock_service, method_name, Mock(return_value=mock_result))
        
        mock_model_data = Mock()
        results = run_evaluations_parallel(mock_model_data, max_workers=2)
        
        assert len(results) >= 8


def test_main_module_as_script_executes(tmp_path, monkeypatch, capsys):
    """Execute main.py as __main__ with patched modules."""
    import runpy

    # Create a temporary input file
    input_file = tmp_path / "input.txt"
    input_file.write_text("https://huggingface.co/testorg/test-model\n")

    # Provide dummy Controllers.Controller module
    mod_controllers = types.ModuleType('Controllers.Controller')
    class FakeController:
        def __init__(self, *a, **k): pass
        def fetch(self, *a, **k): return Mock()
    mod_controllers.Controller = FakeController
    sys.modules['Controllers.Controller'] = mod_controllers

    # Provide dummy Services.Metric_Model_Service module
    mod_service = types.ModuleType('Services.Metric_Model_Service')
    
    # Updated FakeService with ALL methods required by main.py
    class FakeService:
        def __init__(self): pass
        def EvaluatePerformanceClaims(self, md): return Mock(value=0.5)
        def EvaluateBusFactor(self, md): return Mock(value=0.5)
        def EvaluateSize(self, md): return Mock(value=0.5)
        def EvaluateRampUpTime(self, md): return Mock(value=0.5)
        def EvaluateDatasetAndCodeAvailabilityScore(self, md): return Mock(value=0.5)
        def EvaluateCodeQuality(self, md): return Mock(value=0.5)
        def EvaluateDatasetsQuality(self, md): return Mock(value=0.5)
        def EvaluateLicense(self, md): return Mock(value=0.5)
        def EvaluateReproducibility(self, md): return Mock(value=0.5) # Added this!

    mod_service.ModelMetricService = FakeService
    sys.modules['Services.Metric_Model_Service'] = mod_service

    monkeypatch.setattr(sys, 'argv', ['main.py', str(input_file)])

    runpy.run_path(os.path.join(os.path.dirname(__file__), '..', 'main.py'), run_name='__main__')

    captured = capsys.readouterr()
    assert captured.out.strip() != ""