"""
Comprehensive coverage tests for Metric_Model_Service.py.
Targets 100% line coverage by hitting all branches, error handlers, and edge cases.
"""
import sys
import os
import pytest
import json
from unittest.mock import Mock, patch, mock_open
from datetime import datetime, timezone, timedelta

# Ensure backend path is available
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import module to allow patch.object
import Services.Metric_Model_Service
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType

class TestFullServiceCoverage:
    
    def setup_method(self):
        # Use patch.object on the module to safely mock the class
        with patch.object(Services.Metric_Model_Service, 'LLMManager'):
            self.service = Services.Metric_Model_Service.ModelMetricService()

    # =========================================================================
    # 1. EVALUATE MODEL (Placeholder)
    # =========================================================================
    def test_evaluate_model_placeholder(self):
        result = self.service.EvaluateModel("desc", "data")
        assert result.value == 0.0
        assert result.details["info"] == "Model evaluation not yet implemented"

    # =========================================================================
    # 2. PERFORMANCE CLAIMS (Truncation, JSON Parsing, File IO)
    # =========================================================================
    def test_perf_claims_truncation_and_parsing(self):
        """Test text truncation logic and various JSON response formats."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        # Create > 8000 chars to trigger truncation logic
        mock_model.card = "A" * 7000 + "MIDDLE" + "B" * 2000 
        
        # Test clean JSON
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"score": 0.85, "notes": "Solid"}')
            result = self.service.EvaluatePerformanceClaims(mock_model)
            assert result.value == 0.85
            
            # Verify truncation happened in the prompt
            prompt = m.call_args[0][0]
            assert "truncated" in prompt
            assert len(prompt) < 15000 # Should be well below full size

        # Test Markdown JSON
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='```json\n{"score": 0.7}\n```')
            result = self.service.EvaluatePerformanceClaims(mock_model)
            assert result.value == 0.7

    def test_perf_claims_error_handling(self):
        """Test error branches: File IO error, Invalid JSON, Empty Response."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = "dummy.md"
        mock_model.card = ""

        # 1. File Read Error
        with patch('builtins.open', side_effect=IOError("Read fail")):
            with patch.object(self.service.llm_manager, 'call_genai_api') as m:
                m.return_value = Mock(content='{"score": 0.5}')
                # Should proceed with empty README
                result = self.service.EvaluatePerformanceClaims(mock_model)
                assert result.value == 0.5

        # 2. Empty LLM Response
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='')
            result = self.service.EvaluatePerformanceClaims(mock_model)
            assert result.value == 0.0
            assert "Empty response" in result.details['notes']

        # 3. Invalid JSON
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='Not JSON')
            result = self.service.EvaluatePerformanceClaims(mock_model)
            assert result.value == 0.0
            assert "JSON parse error" in result.details['notes']

        # 4. LLM API Failure (Exception)
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=RuntimeError("API Down")):
            with pytest.raises(RuntimeError):
                self.service.EvaluatePerformanceClaims(mock_model)

    # =========================================================================
    # 3. BUS FACTOR (Contributors + Recency Logic)
    # =========================================================================
    def test_bus_factor_logic_matrix(self):
        """Test every branch of contributor and recency scoring."""
        # Contributors: 0, 1, 2-3, 4-6, 7+
        # Recency: <6mo, <12mo, <24mo, <36mo, >36mo, None
        
        scenarios = [
            (0, 0.0), (1, 0.5), (2, 0.6), (5, 0.8), (10, 1.0)
        ]
        now = datetime.now(timezone.utc)

        for count, expected_c_score in scenarios:
            mock_model = Mock(spec=Model)
            mock_model.repo_contributors = [{"contributions": 1} for _ in range(count)]
            mock_model.repo_commit_history = []
            
            # Recency is None -> 0.5
            result = self.service.EvaluateBusFactor(mock_model)
            assert result.details['contributors_score'] == expected_c_score

        recency_scenarios = [
            (30, 1.0), (200, 0.9), (400, 0.8), (800, 0.7), (1200, 0.6)
        ]
        for days, expected_r_score in recency_scenarios:
            mock_model = Mock(spec=Model)
            mock_model.repo_contributors = []
            date_str = (now - timedelta(days=days)).isoformat()
            mock_model.repo_commit_history = [{"commit": {"author": {"date": date_str}}}]
            
            result = self.service.EvaluateBusFactor(mock_model)
            assert result.details['recency_score'] == expected_r_score

    def test_bus_factor_edge_cases(self):
        """Test None inputs and invalid dates."""
        mock_model = Mock(spec=Model)
        # Invalid contributors list
        mock_model.repo_contributors = None
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.value == 0.15 # 0.7*0 + 0.3*0.5

        # Invalid date format
        mock_model.repo_contributors = []
        mock_model.repo_commit_history = [{"commit": {"author": {"date": "bad-date"}}}]
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.details['recency_score'] == 0.5

        # Missing 'commit' key structure
        mock_model.repo_commit_history = [{"wrong": "structure"}]
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.details['recency_score'] == 0.5

    # =========================================================================
    # 4. SIZE (Parsing & Bands)
    # =========================================================================
    def test_size_parsing_logic(self):
        """Test all size parsing branches."""
        # 1. String GB
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size": "2GB"}
        res = self.service.EvaluateSize(mock_model)
        assert res.details['derived_size_mb'] == 2048.0

        # 2. String MB
        mock_model.repo_metadata = {"size": "500"}
        res = self.service.EvaluateSize(mock_model)
        assert res.details['derived_size_mb'] == 500.0

        # 3. Float/Int
        mock_model.repo_metadata = {"size": 100}
        res = self.service.EvaluateSize(mock_model)
        assert res.details['derived_size_mb'] == 100.0

        # 4. Invalid String
        mock_model.repo_metadata = {"size": "not-a-number"}
        with pytest.raises(RuntimeError):
            self.service.EvaluateSize(mock_model)

        # 5. Invalid Dict
        mock_model.repo_metadata = "Not a dict"
        res = self.service.EvaluateSize(mock_model)
        assert res.value == 0.0
        assert "not a dictionary" in res.details['error']

    def test_size_bands(self):
        """Test the 4 size bands (RPi, Nano, PC, AWS)."""
        # Band 1: Small (<200MB) -> 1.0
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size": 100}
        assert self.service.EvaluateSize(mock_model).value == 1.0

        # Band 2: Medium (1GB) -> Nano ok
        mock_model.repo_metadata = {"size": 1000}
        # Calculation: (0.3(RPi) + 1.0(Nano) + 1.0(PC) + 1.0(AWS)) / 4 = 0.825
        assert self.service.EvaluateSize(mock_model).value > 0.5

        # Band 3: Large (10GB)
        mock_model.repo_metadata = {"size": 10000}
        assert self.service.EvaluateSize(mock_model).value > 0.0

        # Band 4: Huge (100GB)
        mock_model.repo_metadata = {"size": 100000}
        assert self.service.EvaluateSize(mock_model).value > 0.0

    # =========================================================================
    # 5. LICENSE (Rule-based & LLM)
    # =========================================================================
    def test_license_rule_logic(self):
        """Hit the permissive/restrictive dictionaries."""
        # Permissive
        for lic in ["MIT", "Apache-2.0", "BSD-3-Clause", "Unlicense"]:
            mock_model = Mock(spec=Model)
            mock_model.card = {"license": lic}
            mock_model.repo_metadata = {}
            mock_model.readme_path = None
            res = self.service.EvaluateLicense(mock_model)
            assert res.value == 1.0
            assert res.details['classification_method'] == "rule_based"

        # Restrictive
        for lic in ["GPL-3.0", "CC-BY-NC"]:
            mock_model = Mock(spec=Model)
            mock_model.card = {"license": lic}
            mock_model.repo_metadata = {}
            mock_model.readme_path = None
            res = self.service.EvaluateLicense(mock_model)
            assert res.value == 0.0

        # Keyword trigger
        mock_model = Mock(spec=Model)
        mock_model.card = {"license": "Custom Copyright Terms"}
        mock_model.repo_metadata = {}
        mock_model.readme_path = None
        
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"permissiveness_score": 0.5}')
            res = self.service.EvaluateLicense(mock_model)
            assert res.value == 0.5
            assert res.details['classification_method'] == "llm_analysis"

    def test_license_sources(self):
        """Test extraction from repo_metadata vs card."""
        # Source 1: repo_metadata (dict)
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"license": {"name": "MIT", "key": "mit"}}
        mock_model.card = {}
        mock_model.readme_path = None
        res = self.service.EvaluateLicense(mock_model)
        assert res.value == 1.0

        # Source 2: repo_metadata (string)
        mock_model.repo_metadata = {"license": "MIT"}
        res = self.service.EvaluateLicense(mock_model)
        assert res.value == 1.0

    # =========================================================================
    # 6. CODE QUALITY (Heuristics)
    # =========================================================================
    def test_code_quality_heuristics(self):
        """Test fallback heuristics logic."""
        mock_model = Mock(spec=Model)
        mock_model.code_link = "http://github.com"
        mock_model.repo_contents = [
            {"name": "test_app.py", "path": "test_app.py", "type": "file"},
            {"name": "requirements.txt", "path": "requirements.txt", "type": "file"},
            {"name": "README.md", "path": "README.md", "type": "file"},
            {"name": "src", "path": "src/", "type": "dir"},
            {"name": "docs", "path": "docs/", "type": "dir"}
        ]

        # Force LLM failure
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
            res = self.service.EvaluateCodeQuality(mock_model)
            # 0.3(test) + 0.2(dep) + 0.25(struct) + 0.25(docs) = 1.0
            assert res.value >= 0.9
            assert res.details['has_tests'] is True

    # =========================================================================
    # 7. DATASET QUALITY
    # =========================================================================
    def test_dataset_quality_logic(self):
        """Test dataset composition and scoring."""
        mock_model = Mock(spec=Model)
        mock_model.dataset_cards = {"d1": "card1"}
        mock_model.dataset_infos = {"d1": "info1"}

        # Success path
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"has_comprehensive_card": true, "has_clear_data_source": true, "has_preprocessing_info": true, "has_large_size": true}')
            res = self.service.EvaluateDatasetsQuality(mock_model)
            assert res.value == 1.0

        # Empty path
        mock_model.dataset_cards = {}
        mock_model.dataset_infos = {}
        res = self.service.EvaluateDatasetsQuality(mock_model)
        assert res.value == 0.5
        assert res.details['mode'] == "no_data"

    # =========================================================================
    # 8. RAMP UP TIME
    # =========================================================================
    def test_ramp_up_logic(self):
        """Test ramp up time file reading and JSON handling."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        mock_model.card = "Documentation"

        # Success
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"quality_of_example_code": 1.0, "readme_coverage": 1.0}')
            res = self.service.EvaluateRampUpTime(mock_model)
            assert res.value == 1.0

        # No docs
        mock_model.card = ""
        res = self.service.EvaluateRampUpTime(mock_model)
        assert res.value == 0.0

        # JSON array response (handling weird LLM output)
        mock_model.card = "Doc"
        with patch.object(self.service.llm_manager, 'call_genai_api') as m:
            m.return_value = Mock(content='{"quality_of_example_code": [0.5], "readme_coverage": [0.5]}')
            res = self.service.EvaluateRampUpTime(mock_model)
            assert res.value == 0.5

    # =========================================================================
    # 9. AVAILABILITY & REPRODUCIBILITY (Regex)
    # =========================================================================
    def test_availability_and_reproducibility(self):
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        mock_model.card = """
        Dataset: huggingface.co/datasets/a/b
        Code: github.com/a/b
        
        ## Installation
        pip install x
        
        ## Usage
        ```python
        import x
        model = x.load()
        model.predict()
        ```
        """
        
        # Availability
        res_av = self.service.EvaluateDatasetAndCodeAvailabilityScore(mock_model)
        assert res_av.value > 0.5

        # Reproducibility
        res_rep = self.service.EvaluateReproducibility(mock_model)
        assert res_rep.value == 1.0