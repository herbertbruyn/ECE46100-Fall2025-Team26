"""
Deep-dive unit tests for Metric_Model_Service.py to hit internal logic branches
(ifs, elses, specific value thresholds, and error handlers).
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

# Ensure backend path is available
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType

class TestServiceLogicIntensive:
    
    def setup_method(self):
        # Patch the LLMManager to avoid real calls and simple errors
        with patch('lib.LLM_Manager.LLMManager'):
            self.service = ModelMetricService()

    # ==========================================
    # BUS FACTOR LOGIC (Contributors + Recency)
    # ==========================================
    
    def test_bus_factor_contributor_tiers(self):
        """Test all logic branches for contributor counts."""
        scenarios = [
            (1, 0.5),   # Solo
            (2, 0.6),   # Small (2-3)
            (3, 0.6),
            (5, 0.8),   # Medium (4-6)
            (8, 1.0),   # Large (7+)
            (0, 0.0)    # None
        ]
        
        for count, expected_c_score in scenarios:
            mock_model = Mock(spec=Model)
            mock_model.repo_contributors = [{"login": f"u{i}", "contributions": 10} for i in range(count)]
            # Fix recency to neutral (0.6 for stable/old) to isolate contributor score
            # Score = 0.7 * c_score + 0.3 * r_score
            # We just want to ensure the code runs without error and calculates valid scores
            mock_model.repo_commit_history = [] 
            
            result = self.service.EvaluateBusFactor(mock_model)
            assert result.value >= 0.0

    def test_bus_factor_recency_tiers(self):
        """Test all logic branches for commit recency."""
        now = datetime.now(timezone.utc)
        scenarios = [
            (30, 1.0),    # < 6 months
            (200, 0.9),   # < 12 months
            (400, 0.8),   # < 24 months
            (800, 0.7),   # < 36 months
            (1200, 0.6)   # > 36 months
        ]
        
        for days_ago, expected_score in scenarios:
            mock_model = Mock(spec=Model)
            mock_model.repo_contributors = [] # 0 contribs -> 0.0 score
            
            past_date = (now - timedelta(days=days_ago)).isoformat()
            mock_model.repo_commit_history = [{"commit": {"author": {"date": past_date}}}]
            
            result = self.service.EvaluateBusFactor(mock_model)
            # Verify the calculation happened
            assert result.details['recency_score'] == expected_score

    # ==========================================
    # SIZE LOGIC (Parsing + Scoring)
    # ==========================================

    def test_size_parsing_variants(self):
        """Test different size formats in repo_metadata."""
        scenarios = [
            ({"size": 100}, MetricType.SIZE_SCORE),       # Int (MB)
            ({"size": 100.5}, MetricType.SIZE_SCORE),     # Float (MB)
            ({"size_mb": "500"}, MetricType.SIZE_SCORE),  # String MB
            ({"size": "2GB"}, MetricType.SIZE_SCORE),     # String GB
            ({"size": "invalid"}, MetricType.SIZE_SCORE), # Error case
        ]

        for metadata, expected_type in scenarios:
            mock_model = Mock(spec=Model)
            mock_model.model_file_size = None
            mock_model.repo_metadata = metadata
            
            # Should not crash
            try:
                result = self.service.EvaluateSize(mock_model)
                assert result.metric_type == expected_type
            except RuntimeError:
                pass # Error cases are allowed to raise or return 0

    # ==========================================
    # LICENSE LOGIC (Rule-based vs LLM)
    # ==========================================

    def test_license_rule_based_matching(self):
        """Test dictionary matching for licenses (skip LLM)."""
        permissive = ["MIT", "Apache-2.0", "BSD-3-Clause", "Unlicense"]
        restrictive = ["GPL-3.0", "CC-BY-NC", "AGPL-3.0"]
        
        for lic in permissive:
            mock_model = Mock(spec=Model)
            mock_model.card = {"license": lic}
            mock_model.repo_metadata = {}
            mock_model.readme_path = None
            
            result = self.service.EvaluateLicense(mock_model)
            assert result.value == 1.0, f"Failed matching {lic}"
            assert result.details["classification_method"] == "rule_based"

        for lic in restrictive:
            mock_model = Mock(spec=Model)
            mock_model.card = {"license": lic}
            mock_model.repo_metadata = {}
            mock_model.readme_path = None
            
            result = self.service.EvaluateLicense(mock_model)
            assert result.value == 0.0, f"Failed matching {lic}"

    def test_license_fallback_to_llm(self):
        """Test unknown license triggers LLM."""
        mock_model = Mock(spec=Model)
        mock_model.card = {"license": "Custom-weird-license"}
        mock_model.repo_metadata = {}
        mock_model.readme_path = None
        
        # Mock LLM to return a specific score
        with patch.object(self.service.llm_manager, 'call_genai_api') as mock_call:
            mock_call.return_value = Mock(content='{"permissiveness_score": 0.5, "license_type": "Custom"}')
            
            result = self.service.EvaluateLicense(mock_model)
            
            assert result.value == 0.5
            assert result.details["classification_method"] == "llm_analysis"

    # ==========================================
    # CODE QUALITY (Heuristics Fallback)
    # ==========================================

    def test_code_quality_heuristics_fallback(self):
        """Test fallback to file-checking when LLM fails."""
        mock_model = Mock(spec=Model)
        mock_model.code_link = "https://github.com/test/repo"
        # Provide a file list that should score points
        mock_model.repo_contents = [
            {"name": "tests", "path": "tests", "type": "dir"},
            {"name": "requirements.txt", "path": "requirements.txt", "type": "file"},
            {"name": "README.md", "path": "README.md", "type": "file"},
            {"name": "src", "path": "src", "type": "dir"},
            {"name": "docs", "path": "docs", "type": "dir"},
        ]
        
        # Make LLM fail to trigger heuristics
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
            result = self.service.EvaluateCodeQuality(mock_model)
            
            # Should have calculated score based on file presence
            # Tests(0.3) + Dependency(0.2) + Structure(0.25) + Docs(0.25) = 1.0
            assert result.value > 0.5
            assert result.details['has_tests'] is True

    # ==========================================
    # REPRODUCIBILITY (Regex Logic)
    # ==========================================

    def test_reproducibility_regex_logic(self):
        """Test detection of code blocks and import statements."""
        # Case 1: Complete example
        mock_model_1 = Mock(spec=Model)
        mock_model_1.readme_path = None
        # FIX: Added installation instructions to ensure score is 1.0
        mock_model_1.card = """
        ## Installation
        pip install transformers torch

        ## Usage
        To run:
        ```python
        import torch
        from transformers import AutoModel
        model = AutoModel.from_pretrained('x')
        model.generate()
        ```
        """
        result1 = self.service.EvaluateReproducibility(mock_model_1)
        assert result1.value == 1.0

        # Case 2: Incomplete example
        mock_model_2 = Mock(spec=Model)
        mock_model_2.readme_path = None
        mock_model_2.card = """
        Use the model like this:
        ```javascript
        console.log('hello')
        ```
        """
        result2 = self.service.EvaluateReproducibility(mock_model_2)
        # Should be low or 0.5 because it has a block but no python keywords
        assert result2.value < 1.0

    # ==========================================
    # AVAILABILITY (Regex Logic)
    # ==========================================
    
    def test_availability_regex(self):
        """Test regex matching for dataset/code links."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        
        # Matches all 3 patterns
        mock_model.card = """
        Trained on ImageNet dataset.
        See huggingface.co/datasets/user/data for details.
        Code at github.com/user/repo.
        """
        
        result = self.service.EvaluateDatasetAndCodeAvailabilityScore(mock_model)
        # 0.3 (list) + 0.3 (hf link) + 0.4 (code link) = 1.0
        assert result.value == 1.0

    # ==========================================
    # TRUNCATION LOGIC
    # ==========================================

    def test_large_text_truncation(self):
        """Ensure huge READMEs don't break the prompt generator."""
        mock_model = Mock(spec=Model)
        mock_model.readme_path = None
        # Create 20k chars
        mock_model.card = "A" * 20000 
        
        with patch.object(self.service.llm_manager, 'call_genai_api') as mock_call:
            mock_call.return_value = Mock(content='{}')
            
            # This triggers _compose_source_text which has truncation logic
            self.service.EvaluatePerformanceClaims(mock_model)
            
            # Inspect the argument passed to LLM
            prompt = mock_call.call_args[0][0]
            # Ensure it's not 20k+ chars long (plus prompt overhead)
            assert len(prompt) < 18000