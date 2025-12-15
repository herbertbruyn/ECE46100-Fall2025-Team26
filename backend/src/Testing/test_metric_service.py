"""
Unit tests for the ModelMetricService class.
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from Models.Model import Model
from lib.Metric_Result import MetricResult, MetricType

class TestModelMetricService:

    def setup_method(self):
        with patch('lib.LLM_Manager.LLMManager'):
            self.service = ModelMetricService()

    def test_initialization(self):
        assert self.service is not None

    def test_bus_factor_medium_contributors_old_commits(self):
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = [{"login": f"user{i}", "contributions": 5} for i in range(5)]
        old_date = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        mock_model.repo_commit_history = [{"commit": {"author": {"date": old_date}}}]
        
        result = self.service.EvaluateBusFactor(mock_model)
        # 0.7 score logic matched
        assert result.details["contributors_score"] == 0.8

    def test_bus_factor_low_contributors_very_old_commits(self):
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = [{"login": "u1", "contributions": 1}, {"login": "u2", "contributions": 1}]
        old_date = (datetime.now(timezone.utc) - timedelta(days=450)).isoformat()
        mock_model.repo_commit_history = [{"commit": {"author": {"date": old_date}}}]
        
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.details["contributors_score"] == 0.6

    def test_bus_factor_single_contributor(self):
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = [{"login": "solo", "contributions": 10}]
        mock_model.repo_commit_history = [{"commit": {"author": {"date": datetime.now(timezone.utc).isoformat()}}}]
        
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.details["contributors_score"] == 0.5

    def test_bus_factor_no_contributors(self):
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = []
        mock_model.repo_commit_history = []
        
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.value == 0.15

    def test_bus_factor_invalid_commit_date(self):
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = [{"login": "u1", "contributions": 1}]
        mock_model.repo_commit_history = [{"commit": {"author": {"date": "bad"}}}]
        
        result = self.service.EvaluateBusFactor(mock_model)
        assert result.details["recency_score"] == 0.5