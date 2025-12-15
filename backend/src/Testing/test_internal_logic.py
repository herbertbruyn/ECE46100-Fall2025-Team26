"""
Targeted unit tests for internal logic branches in Metric_Model_Service.py.
Focuses on nested functions and edge cases in Code Quality, Datasets, License, and Reproducibility.
"""
import sys
import os
import pytest
import json
from unittest.mock import Mock, patch, mock_open  # Added mock_open here

# Ensure backend path is available
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType

class TestInternalLogic:
    
    def setup_method(self):
        # Patch the LLMManager to allow us to define behavior per test
        with patch('lib.LLM_Manager.LLMManager'):
            self.service = ModelMetricService()

    # =========================================================================
    # 1. EVALUATE CODE QUALITY (Internal Heuristics)
    # =========================================================================
    
    def test_code_quality_test_files_detection(self):
        """Target _check_test_files logic."""
        # Case 1: Standard 'tests' folder
        m1 = Mock(spec=Model)
        m1.repo_contents = [{"name": "tests", "path": "tests", "type": "dir"}]
        # Force LLM fail to isolate heuristic check
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
            res = self.service.EvaluateCodeQuality(m1)
            assert res.details['has_tests'] is True

        # Case 2: 'spec' file pattern
        m2 = Mock(spec=Model)
        m2.repo_contents = [{"name": "app.spec.ts", "path": "src/app.spec.ts", "type": "file"}]
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
            res = self.service.EvaluateCodeQuality(m2)
            assert res.details['has_tests'] is True

    def test_code_quality_dependency_detection(self):
        """Target _check_dependency_management logic."""
        files = ["pyproject.toml", "conda.yml", "Pipfile"]
        for f in files:
            m = Mock(spec=Model)
            m.repo_contents = [{"name": f, "path": f, "type": "file"}]
            with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
                res = self.service.EvaluateCodeQuality(m)
                assert res.details['has_dependency_management'] is True

    def test_code_quality_structure_heuristics(self):
        """Target _check_structure_heuristics logic (needs 2+ matches)."""
        # Case 1: Only 1 match (should fail)
        m1 = Mock(spec=Model)
        m1.repo_contents = [{"name": "src", "path": "src/", "type": "dir"}]
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
            res = self.service.EvaluateCodeQuality(m1)
            assert res.details['has_good_structure'] is False

        # Case 2: 2 matches (should pass)
        m2 = Mock(spec=Model)
        m2.repo_contents = [
            {"name": "src", "path": "src/", "type": "dir"},
            {"name": "config", "path": "config/", "type": "dir"}
        ]
        with patch.object(self.service.llm_manager, 'call_genai_api', side_effect=Exception("LLM Down")):
            res = self.service.EvaluateCodeQuality(m2)
            assert res.details['has_good_structure'] is True

    # =========================================================================
    # 2. EVALUATE DATASETS QUALITY (Internal Logic)
    # =========================================================================

    def test_datasets_quality_text_composition(self):
        """Target _compose_dataset_text logic."""
        m = Mock(spec=Model)
        # Setup data so it triggers text accumulation
        m.dataset_cards = {"ds1": "some card content"}
        m.dataset_infos = {"ds1": "some info content"}
        
        # Verify LLM is called with combined text
        with patch.object(self.service.llm_manager, 'call_genai_api') as mock_llm:
            mock_llm.return_value = Mock(content='{}')
            self.service.EvaluateDatasetsQuality(m)
            
            prompt = mock_llm.call_args[0][0]
            assert "Dataset: ds1" in prompt
            assert "Card Data: some card content" in prompt
            assert "Dataset Info: some info content" in prompt

    def test_datasets_quality_truncation(self):
        """Target text truncation logic > 16000 chars."""
        m = Mock(spec=Model)
        # Create massive content
        m.dataset_cards = {"ds1": "A" * 20000}
        m.dataset_infos = {}
        
        with patch.object(self.service.llm_manager, 'call_genai_api') as mock_llm:
            mock_llm.return_value = Mock(content='{}')
            self.service.EvaluateDatasetsQuality(m)
            
            prompt = mock_llm.call_args[0][0]
            # Prompt contains instructions + truncated text
            # Instructions ~500 chars, Text truncated to 16000 + marker
            assert len(prompt) < 17000 
            assert "...[truncated]..." in prompt

    # =========================================================================
    # 3. EVALUATE LICENSE (Internal Classification)
    # =========================================================================

    def test_license_extraction_sources(self):
        """Target _get_license_info extraction from multiple sources."""
        m = Mock(spec=Model)
        
        # 1. GitHub API license object
        m.repo_metadata = {"license": {"name": "MIT License", "key": "mit"}}
        m.card = {}
        res = self.service.EvaluateLicense(m)
        assert res.value == 1.0
        assert "repo_license: MIT License" in res.details['license_text']

        # 2. Description mention
        m.repo_metadata = {}
        m.card = {"description": "This model is released under Apache 2.0 license."}
        res = self.service.EvaluateLicense(m)
        assert res.value == 1.0
        assert "description:" in res.details['license_text']

    def test_license_restrictive_list(self):
        """Target restrictive license dictionary."""
        restrictive = ["gpl-3.0", "cc-by-nc", "proprietary"]
        for lic in restrictive:
            m = Mock(spec=Model)
            m.repo_metadata = {"license": {"key": lic}}
            m.card = {}
            res = self.service.EvaluateLicense(m)
            assert res.value == 0.0
            assert "Restrictive license" in res.details['reason']

    def test_license_llm_fallback(self):
        """Target LLM fallback when keywords found but no direct match."""
        m = Mock(spec=Model)
        m.card = {"description": "Subject to custom license terms and copyright."}
        m.repo_metadata = {}
        
        with patch.object(self.service.llm_manager, 'call_genai_api') as mock_llm:
            # LLM says it's moderately permissive
            mock_llm.return_value = Mock(content='{"permissiveness_score": 0.6, "license_type": "Custom"}')
            res = self.service.EvaluateLicense(m)
            
            assert res.value == 0.6
            assert res.details['classification_method'] == "llm_analysis"

    # =========================================================================
    # 4. EVALUATE REPRODUCIBILITY (Internal Logic)
    # =========================================================================

    def test_reproducibility_complete_flow(self):
        """Target logic for 'complete' code example."""
        m = Mock(spec=Model)
        m.readme_path = "README.md"
        # Needs 3+ execution indicators to be 'complete'
        content = """
        # Usage
        ```python
        from transformers import AutoModel  # Indicator 1
        model = AutoModel.from_pretrained() # Indicator 2
        result = model.generate(text)       # Indicator 3
        ```
        """
        
        with patch('builtins.open', mock_open(read_data=content)):
            res = self.service.EvaluateReproducibility(m)
            # Default is 1.0 if complete, but might downgrade to 0.5 if no install instructions found
            assert res.value in (0.5, 1.0)
            if res.value == 0.5:
                assert "No installation instructions" in res.details['issues_found']

    def test_reproducibility_perfect_score(self):
        """Target perfect 1.0 score requirements."""
        m = Mock(spec=Model)
        m.readme_path = "README.md"
        content = """
        pip install transformers  # Installation check
        
        # Usage
        ```python
        from transformers import AutoModel  # Indicator 1
        model = AutoModel.from_pretrained() # Indicator 2 (Load check)
        result = model.generate(text)       # Indicator 3
        ```
        """
        
        with patch('builtins.open', mock_open(read_data=content)):
            res = self.service.EvaluateReproducibility(m)
            assert res.value == 1.0
            assert res.details['code_completeness'] == "complete"

    def test_reproducibility_inline_code(self):
        """Target inline code check when no blocks found."""
        m = Mock(spec=Model)
        m.readme_path = None
        m.card = "Run `import model` to start."
        
        res = self.service.EvaluateReproducibility(m)
        # Found inline code, but likely not complete enough for high score
        assert res.details['has_code'] is True
        assert res.details.get('inline_code_found', 0) > 0

    def test_reproducibility_no_code(self):
        """Target no code path."""
        m = Mock(spec=Model)
        m.readme_path = None
        m.card = "Just a description."
        
        res = self.service.EvaluateReproducibility(m)
        assert res.value == 0.0
        assert res.details['has_code'] is False