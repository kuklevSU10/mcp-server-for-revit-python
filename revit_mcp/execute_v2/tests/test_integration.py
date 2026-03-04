"""
Integration tests for execute_v2 pipeline using mocked Revit doc/uidoc.
These test the full pipeline flow (Intent -> Context -> Generate -> Validate -> Execute -> Format)
without requiring a live Revit instance.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent paths so imports work without package install
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from revit_mcp.execute_v2.pipeline import ExecuteV2Pipeline
from revit_mcp.execute_v2.session_state import SessionManager

INTEGRATION_PROMPTS = [
    ("найди все стены", "read"),
    ("посчитай двери по этажам", "read"),
    ("переименуй помещения по шаблону", "write"),
    ("найди элементы без маркировки", "read"),
    ("установи комментарий всем стенам", "write"),
    ("покажи статистику проекта", "read"),
    ("найди дубликаты комнат", "read"),
    ("площадь помещений по уровням", "read"),
    ("скопируй тип в комментарии", "write"),
    ("создай спецификацию дверей", "write"),
]

class TestIntegration:
    def setup_method(self):
        # Reset singleton managers to ensure clean state
        SessionManager._reset()
        
        # We patch the code generator to avoid making real LLM calls during CI
        # If OPENROUTER_API_KEY is present and testing is run manually, this could be skipped
        self.pipeline = ExecuteV2Pipeline(openrouter_key="dummy_key", log_dir="test_logs")
        
        # Mocks
        self.doc = MagicMock()
        self.doc.ProjectInformation.Name = "Test Project"
        self.doc.Application.VersionNumber = "2024"
        self.doc.ActiveView.Name = "Level 1"
        self.doc.ActiveView.ViewType = "FloorPlan"
        self.doc.IsWorkshared = False
        
        self.uidoc = MagicMock()
        self.DB = MagicMock()
        self.revit = MagicMock()

    @patch("revit_mcp.execute_v2.code_generator.CodeGenerator.generate")
    @patch("revit_mcp.execute_v2.transaction_executor.TransactionExecutor.execute")
    @pytest.mark.parametrize("prompt, expected_intent", INTEGRATION_PROMPTS)
    def test_pipeline_integration_mocked(self, mock_execute, mock_generate, prompt, expected_intent):
        """Test full pipeline routing, parsing, and execution logic using mocks."""
        
        # Setup mock code generation
        mock_generate.return_value = {
            "code": "__result__ = {'summary': 'Mocked success', 'count': 5}",
            "raw_response": "Mocked LLM response"
        }
        
        # Setup mock execution
        mock_execute.return_value = {
            "status": "success",
            "output": "",
            "result": {"summary": "Mocked success", "count": 5},
            "__result__": {"summary": "Mocked success", "count": 5}
        }
        
        result = self.pipeline.run(
            user_request=prompt,
            doc=self.doc,
            uidoc=self.uidoc,
            DB=self.DB,
            revit=self.revit,
            session_id="test-session-int"
        )
        
        assert result["status"] == "success"
        assert result["intent"]["intent_type"] == expected_intent
        assert "Mocked success" in result["response"]
        
        # Verify call arguments
        mock_generate.assert_called_once()
        args, kwargs = mock_generate.call_args
        assert prompt in args[0]  # request (might be augmented with history)
        assert isinstance(args[1], dict)  # context
        assert args[2] == expected_intent  # intent_type
        
        mock_execute.assert_called_once()

    @patch("revit_mcp.execute_v2.code_generator.CodeGenerator.generate")
    @patch("revit_mcp.execute_v2.transaction_executor.TransactionExecutor.execute")
    def test_multi_step_integration(self, mock_execute, mock_generate):
        """Test the multi-step integration flow."""
        
        mock_generate.return_value = {
            "code": "__result__ = [1, 2, 3]",
            "raw_response": "Mocked LLM response"
        }
        
        mock_execute.return_value = {
            "status": "success",
            "output": "",
            "result": [1, 2, 3],
            "__result__": [1, 2, 3]
        }
        
        prompt = "сначала найди двери на 1 этаже, а потом переименуй их"
        
        # Should be delegated to MultiStepExecutor automatically by Pipeline
        result = self.pipeline.run(
            user_request=prompt,
            doc=self.doc,
            uidoc=self.uidoc,
            DB=self.DB,
            revit=self.revit,
            session_id="test-multistep"
        )
        
        assert result["status"] == "success"
        # Since it splits into 2 steps, generate and execute should be called twice
        assert mock_generate.call_count == 2
        assert mock_execute.call_count == 2
        
        # Check session state has the elements from step 1
        session = SessionManager.get_instance().get_or_create("test-multistep")
        elements = session.get_elements("last_result")
        assert len(elements) == 0  # Actually pipeline _execute_pipeline puts it in last_result
        # The multi step executor saves it as step_0_result
        step0_elements = session.get_elements("step_0_result")
        assert step0_elements == [1, 2, 3]
