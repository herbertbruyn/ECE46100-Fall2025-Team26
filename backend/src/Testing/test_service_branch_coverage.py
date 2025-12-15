import json
import pytest
from unittest.mock import Mock, patch
from Services.Metric_Model_Service import ModelMetricService
from lib.Metric_Result import MetricResult, MetricType
from Models.Model import Model


class TestServiceBranchCoverage:
    def setup_method(self):
        with patch('lib.LLM_Manager.LLMManager'):
            self.service = ModelMetricService()
        # Stub llm_manager for deterministic behavior
        self.service.llm_manager = Mock()

    def test_performance_claims_parses_fenced_json(self):
        # Response with fenced json (```json ... ```)
        fenced = """```json\n{\n \"score\": 0.65, \"notes\": \"fenced\"\n}\n```"""
        resp = Mock()
        resp.content = fenced
        self.service.llm_manager.call_genai_api.return_value = resp

        model = Mock(spec=Model)
        model.card = "Some metrics"
        model.readme_path = None

        result = self.service.EvaluatePerformanceClaims(model)
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
        assert 0 <= result.value <= 1
        assert result.details.get("notes") == "fenced"

    def test_performance_claims_handles_bad_json(self):
        # Malformed JSON should yield score 0.0 and notes with parse error
        bad = "not-json"
        resp = Mock()
        resp.content = bad
        self.service.llm_manager.call_genai_api.return_value = resp

        model = Mock(spec=Model)
        model.card = "Benchmark: 90%"
        model.readme_path = None

        result = self.service.EvaluatePerformanceClaims(model)
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
        assert result.value == 0.0
        assert "JSON parse error" in result.details.get("notes", "")

    def test_size_parses_gb_string(self):
        # repo_metadata with size as GB string
        model = Mock(spec=Model)
        model.repo_metadata = {"size": "64GB"}
        result = self.service.EvaluateSize(model)
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.SIZE_SCORE
        assert 0 <= result.value <= 1
        # derived size should be MB
        assert result.details.get("derived_size_mb") == 64 * 1024

    def test_size_invalid_mb_string_raises_runtime(self):
        # invalid MB string triggers error path
        model = Mock(spec=Model)
        model.repo_metadata = {"size": "invalidMB"}
        with patch('logging.error') as mock_log_error:
            with pytest.raises(RuntimeError):
                self.service.EvaluateSize(model)
        # Ensure error was logged
        assert mock_log_error.called
