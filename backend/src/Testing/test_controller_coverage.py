"""
Coverage tests for Controller.py
"""
import sys
import os
import pytest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from Controllers.Controller import Controller
from Models.Model import Model

class TestControllerCoverage:
    
    # PATCH THE CLASS WHERE IT IS IMPORTED IN CONTROLLER.PY
    # This ensures the Controller uses the Mock, not the real class
    @patch('Controllers.Controller.ModelManager')
    def test_fetch_basic_functionality(self, mock_manager_cls):
        """Test the basic fetch delegation to ModelManager."""
        mock_instance = mock_manager_cls.return_value
        expected_model = Mock(spec=Model)
        mock_instance.where.return_value = expected_model
        
        controller = Controller()
        
        result = controller.fetch(
            "https://huggingface.co/test/model",
            dataset_links=["https://data.com"],
            code_link="https://github.com"
        )
        
        assert result == expected_model
        mock_instance.where.assert_called_once()

    @patch('Controllers.Controller.ModelManager')
    def test_fetch_no_datasets(self, mock_manager_cls):
        """Test fetch handles None for optional args."""
        mock_instance = mock_manager_cls.return_value
        
        controller = Controller()
        controller.fetch("https://huggingface.co/test/model")
        
        args = mock_instance.where.call_args
        assert args is not None
        assert args[0][0] == "https://huggingface.co/test/model"
        assert args[0][1] is None
        assert args[0][2] is None

    @patch('Controllers.Controller.ModelManager')
    def test_fetch_api_error_handling(self, mock_manager_cls):
        """Test controller propagates exceptions from manager."""
        mock_instance = mock_manager_cls.return_value
        mock_instance.where.side_effect = RuntimeError("API Down")
        
        controller = Controller()
        
        with pytest.raises(RuntimeError):
            controller.fetch("https://huggingface.co/test/model")