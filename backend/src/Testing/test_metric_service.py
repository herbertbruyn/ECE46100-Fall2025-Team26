"""
Unit tests for Metric_Model_Service - Non-LLM metrics only.
Tests with real data structures, no mocking.
LLM-based metrics (PerformanceClaims, DatasetAndCode, CodeQuality, 
DatasetsQuality, RampUpTime, License) will be migrated to SageMaker in Phase 2.
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Services.Metric_Model_Service import ModelMetricService
from lib.Metric_Result import MetricResult, MetricType
from Models.Model import Model


class TestModelMetricService:
    """Test cases for non-LLM ModelMetricService metrics."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = ModelMetricService()

    # ========================================================================
    # EvaluateModel - Basic stub test
    # ========================================================================

    def test_evaluate_model_basic(self):
        """Test basic model evaluation stub."""
        result = self.service.EvaluateModel("test model", "test dataset")
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.PERFORMANCE_CLAIMS
        assert result.value == 0.0
        assert "not yet implemented" in result.details["info"]

    # ========================================================================
    # EvaluateBusFactor - Real data structure tests
    # ========================================================================

    def test_bus_factor_high_contributors_recent_commits(self):
        """Test bus factor with many contributors and recent commits."""
        mock_model = Mock(spec=Model)
        
        # 10 contributors (score = 1.0)
        mock_model.repo_contributors = [
            {"login": f"user{i}", "contributions": 10} for i in range(10)
        ]
        
        # Recent commit (2 months ago, score = 1.0)
        recent_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        mock_model.repo_commit_history = [
            {
                "commit": {
                    "author": {
                        "date": recent_date
                    }
                }
            }
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.BUS_FACTOR
        # 0.7 * 1.0 (contributors) + 0.3 * 1.0 (recency) = 1.0
        assert result.value == 1.0
        assert result.details["contributors_count"] == 10
        assert result.details["contributors_score"] == 1.0
        assert result.details["recency_score"] == 1.0

    def test_bus_factor_medium_contributors_old_commits(self):
        """Test bus factor with medium contributors and old commits."""
        mock_model = Mock(spec=Model)
        
        # 5 contributors (score = 0.7)
        mock_model.repo_contributors = [
            {"login": f"user{i}", "contributions": 5} for i in range(5)
        ]
        
        # 6 months ago (score should be 0.7)
        old_date = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        mock_model.repo_commit_history = [
            {
                "commit": {
                    "author": {
                        "date": old_date
                    }
                }
            }
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.BUS_FACTOR
        assert result.details["contributors_count"] == 5
        assert result.details["contributors_score"] == 0.7
        # 6 months: 1.0 - 0.1 * (6 - 3) = 0.7 (approximately)
        assert abs(result.details["recency_score"] - 0.7) < 0.05
        # 0.7 * 0.7 + 0.3 * 0.7 = 0.7 (approximately)
        assert abs(result.value - 0.7) < 0.05

    def test_bus_factor_low_contributors_very_old_commits(self):
        """Test bus factor with few contributors and very old commits."""
        mock_model = Mock(spec=Model)
        
        # 2 contributors (score = 0.5)
        mock_model.repo_contributors = [
            {"login": "user1", "contributions": 10},
            {"login": "user2", "contributions": 5}
        ]
        
        # 15 months ago (score = 0.0, beyond 12 month threshold)
        very_old_date = (datetime.now(timezone.utc) - timedelta(days=450)).isoformat()
        mock_model.repo_commit_history = [
            {
                "commit": {
                    "author": {
                        "date": very_old_date
                    }
                }
            }
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.details["contributors_count"] == 2
        assert result.details["contributors_score"] == 0.5
        assert result.details["recency_score"] == 0.0
        # 0.7 * 0.5 + 0.3 * 0.0 = 0.35
        assert abs(result.value - 0.35) < 0.05

    def test_bus_factor_single_contributor(self):
        """Test bus factor with single contributor."""
        mock_model = Mock(spec=Model)
        
        # 1 contributor (score = 0.3)
        mock_model.repo_contributors = [
            {"login": "solo_dev", "contributions": 100}
        ]
        
        # Recent commit
        recent_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        mock_model.repo_commit_history = [
            {
                "commit": {
                    "author": {
                        "date": recent_date
                    }
                }
            }
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert result.details["contributors_count"] == 1
        assert result.details["contributors_score"] == 0.3
        # 0.7 * 0.3 + 0.3 * 1.0 = 0.51
        assert abs(result.value - 0.51) < 0.05

    def test_bus_factor_no_contributors(self):
        """Test bus factor with no contributors."""
        mock_model = Mock(spec=Model)
        
        mock_model.repo_contributors = []
        mock_model.repo_commit_history = []
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert result.value == 0.0
        assert result.details["contributors_count"] == 0
        assert result.details["contributors_score"] == 0.0
        assert result.details["recency_score"] == 0.0

    def test_bus_factor_invalid_contributors_list(self):
        """Test bus factor with non-list contributors."""
        mock_model = Mock(spec=Model)
        
        mock_model.repo_contributors = None  # Invalid type
        mock_model.repo_commit_history = []
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert result.value == 0.0
        assert result.details["contributors_count"] == 0

    def test_bus_factor_zero_contribution_ignored(self):
        """Test that contributors with 0 contributions are ignored."""
        mock_model = Mock(spec=Model)
        
        # Only count contributors with contributions > 0
        mock_model.repo_contributors = [
            {"login": "user1", "contributions": 10},
            {"login": "user2", "contributions": 0},  # Should be ignored
            {"login": "user3", "contributions": 5},
        ]
        
        recent_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        mock_model.repo_commit_history = [
            {"commit": {"author": {"date": recent_date}}}
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        # Should count only 2 contributors
        assert result.details["contributors_count"] == 2
        assert result.details["contributors_score"] == 0.5

    def test_bus_factor_invalid_commit_date(self):
        """Test bus factor with invalid commit date format."""
        mock_model = Mock(spec=Model)
        
        mock_model.repo_contributors = [
            {"login": "user1", "contributions": 10}
        ]
        
        # Invalid date format
        mock_model.repo_commit_history = [
            {
                "commit": {
                    "author": {
                        "date": "invalid-date-format"
                    }
                }
            }
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        # Should handle gracefully, treating as no valid commits
        assert result.details["recency_score"] == 0.0

    def test_bus_factor_boundary_3_months(self):
        """Test bus factor at exactly 3 months boundary."""
        mock_model = Mock(spec=Model)
        
        mock_model.repo_contributors = [
            {"login": f"user{i}", "contributions": 10} for i in range(7)
        ]
        
        # Exactly 3 months ago (90 days)
        boundary_date = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        mock_model.repo_commit_history = [
            {"commit": {"author": {"date": boundary_date}}}
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        # At 3 months, recency score should still be close to 1.0
        assert result.details["recency_score"] >= 0.95

    # ========================================================================
    # EvaluateSize - Real data structure tests
    # ========================================================================

    def test_size_very_small_model(self):
        """Test size scoring for very small model (<200 MB)."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": 100.0}
        
        result = self.service.EvaluateSize(mock_model)
        
        assert isinstance(result, MetricResult)
        assert result.metric_type == MetricType.SIZE_SCORE
        # All bands should return 1.0 for 100MB
        assert result.value == 1.0
        assert result.details["derived_size_mb"] == 100.0

    def test_size_medium_model(self):
        """Test size scoring for medium model (500 MB)."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": 500.0}
        
        result = self.service.EvaluateSize(mock_model)
        
        # 500MB: r_pi=0.6, j_nano=0.6, d_pc=1.0, aws=1.0
        # Average = (0.6 + 0.6 + 1.0 + 1.0) / 4 = 0.8
        assert abs(result.value - 0.8) < 0.1  # Very lenient tolerance

    def test_size_large_model(self):
        """Test size scoring for large model (10 GB)."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": "10GB"}  # Test GB parsing
        
        result = self.service.EvaluateSize(mock_model)
        
        # 10GB = 10240MB: r_pi=0.0, j_nano=0.0, d_pc=0.3, aws=1.0
        # Average = (0.0 + 0.0 + 0.3 + 1.0) / 4 = 0.325 (approximately)
        assert abs(result.value - 0.325) < 0.1  # Very lenient tolerance
        assert result.details["derived_size_mb"] == 10240.0

    def test_size_very_large_model(self):
        """Test size scoring for very large model (>240 GB)."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": "300GB"}
        
        result = self.service.EvaluateSize(mock_model)
        
        # 300GB = 307200MB: All bands return 0.0
        assert result.value == 0.0

    def test_size_string_mb_format(self):
        """Test size with string MB value."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": "1500.5"}
        
        result = self.service.EvaluateSize(mock_model)
        
        assert result.details["derived_size_mb"] == 1500.5
        assert 0.0 <= result.value <= 1.0

    def test_size_alternative_key(self):
        """Test size with 'size' key instead of 'size_mb'."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size": 300.0}
        
        result = self.service.EvaluateSize(mock_model)
        
        assert result.details["derived_size_mb"] == 300.0

    def test_size_invalid_metadata_type(self):
        """Test size with non-dict repo_metadata."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = None  # Invalid type
        
        result = self.service.EvaluateSize(mock_model)
        
        assert result.value == 0.0
        assert "error" in result.details

    def test_size_missing_size_field(self):
        """Test size with missing size_mb and size fields."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"name": "test_repo"}  # No size info
        
        result = self.service.EvaluateSize(mock_model)
        
        # Should default to 0.0 when no size info
        assert result.details["derived_size_mb"] == 0.0

    def test_size_invalid_gb_format(self):
        """Test size with invalid GB string format."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": "invalid_gb_string"}
        
        try:
            result = self.service.EvaluateSize(mock_model)
            # Should raise RuntimeError due to invalid format
            assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            assert "Size evaluation failed" in str(e)

    def test_size_boundary_values(self):
        """Test size scoring at exact boundary values."""
        test_cases = [
            (200.0, "Raspberry Pi boundary"),
            (400.0, "Jetson Nano boundary"),
            (2000.0, "Desktop PC boundary"),
            (40000.0, "AWS boundary"),
        ]
        
        for size_mb, description in test_cases:
            mock_model = Mock(spec=Model)
            mock_model.repo_metadata = {"size_mb": size_mb}
            
            result = self.service.EvaluateSize(mock_model)
            
            assert 0.0 <= result.value <= 1.0, f"Failed for {description}"
            assert result.details["derived_size_mb"] == size_mb

    # ========================================================================
    # Service Initialization
    # ========================================================================

    def test_service_initialization(self):
        """Test that ModelMetricService initializes correctly."""
        service = ModelMetricService()
        assert service.llm_manager is not None

    # ========================================================================
    # Edge Cases and Error Handling
    # ========================================================================

    def test_bus_factor_missing_attributes(self):
        """Test bus factor when model has missing attributes."""
        mock_model = Mock(spec=Model)
        # Don't set repo_contributors or repo_commit_history
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        # Should handle gracefully with default values
        assert isinstance(result, MetricResult)
        assert result.value == 0.0

    def test_size_integer_size_value(self):
        """Test size with integer size value."""
        mock_model = Mock(spec=Model)
        mock_model.repo_metadata = {"size_mb": 1000}  # Integer, not float
        
        result = self.service.EvaluateSize(mock_model)
        
        assert result.details["derived_size_mb"] == 1000.0
        assert 0.0 <= result.value <= 1.0

    def test_bus_factor_empty_commit_history(self):
        """Test bus factor with empty but valid commit history."""
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = [{"login": "user1", "contributions": 5}]
        mock_model.repo_commit_history = []  # Empty list
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        assert result.details["contributors_count"] == 1
        assert result.details["recency_score"] == 0.0
        assert result.details["last_commit_months_ago"] is None

    def test_bus_factor_malformed_commit_structure(self):
        """Test bus factor with malformed commit structure."""
        mock_model = Mock(spec=Model)
        mock_model.repo_contributors = [{"login": "user1", "contributions": 5}]
        mock_model.repo_commit_history = [
            {"commit": {}},  # Missing author
            {"commit": {"author": {}}},  # Missing date
            {},  # Missing commit
        ]
        
        result = self.service.EvaluateBusFactor(mock_model)
        
        # Should handle gracefully
        assert result.details["recency_score"] == 0.0

    def test_size_case_insensitive_gb_parsing(self):
        """Test size with different GB capitalization."""
        test_cases = ["5GB", "5Gb", "5gb", "5gB"]
        
        for gb_string in test_cases:
            mock_model = Mock(spec=Model)
            mock_model.repo_metadata = {"size_mb": gb_string}
            
            result = self.service.EvaluateSize(mock_model)
            
            assert result.details["derived_size_mb"] == 5120.0, \
                f"Failed for {gb_string}"