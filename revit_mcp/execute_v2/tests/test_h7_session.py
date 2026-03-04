import pytest
from revit_mcp.execute_v2.session_state import SessionState

class TestSessionHistory:
    def test_add_to_history(self):
        s = SessionState("hist-1")
        s.add_to_history("user", "Hello")
        assert len(s._history) == 1
        assert s._history[0]["role"] == "user"
        assert s._history[0]["content"] == "Hello"
        
        s.add_to_history("assistant", "World", code="print(1)")
        assert len(s._history) == 2
        assert s._history[1]["code"] == "print(1)"

    def test_get_history_snippet(self):
        s = SessionState("hist-2")
        assert s.get_history_snippet() == ""
        
        for i in range(10):
            s.add_to_history("user", "Q{}".format(i))
            s.add_to_history("assistant", "A{}".format(i))
            
        # Default is 3 turns = 6 messages
        snippet = s.get_history_snippet(max_turns=3)
        assert "User: Q7" in snippet
        assert "Assistant: A9" in snippet
        assert "User: Q6" not in snippet  # Too old
        
    def test_to_prompt_snippet_includes_history(self):
        s = SessionState("hist-3")
        s.add_to_history("user", "My question")
        snippet = s.to_prompt_snippet()
        assert "ИСТОРИЯ ДИАЛОГА" in snippet
        assert "My question" in snippet