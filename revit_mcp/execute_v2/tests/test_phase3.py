"""
Phase 3 unit tests — SessionState, AuditLog, ModelRouter, Pipeline integration.
Pure Python 3, no Revit dependency. All external calls are mocked.
"""

import json
import os
import sys
import tempfile
import time

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# Add parent paths so imports work without package install
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from revit_mcp.execute_v2.session_state import SessionState, SessionManager
from revit_mcp.execute_v2.audit_log import AuditLog
from revit_mcp.execute_v2.model_router import ModelRouter
from revit_mcp.execute_v2.pipeline import ExecuteV2Pipeline
from revit_mcp.execute_v2.transaction_executor import TransactionExecutor


# ── SessionState Tests ──────────────────────────────────────────────

class TestSessionState:

    def test_session_store_and_get(self):
        s = SessionState("test-1")
        s.store_elements([100, 200, 300], "doors")
        assert s.get_elements("doors") == [100, 200, 300]

    def test_session_store_default_label(self):
        s = SessionState("test-2")
        s.store_elements([1, 2, 3])
        assert s.get_elements() == [1, 2, 3]
        assert s.get_elements("last_result") == [1, 2, 3]

    def test_session_get_missing_label(self):
        s = SessionState("test-3")
        assert s.get_elements("nonexistent") == []

    def test_session_context_store_get(self):
        s = SessionState("test-4")
        s.store_context("active_level", "Level 1")
        assert s.get_context("active_level") == "Level 1"
        assert s.get_context("missing", "default") == "default"

    def test_session_clear(self):
        s = SessionState("test-5")
        s.store_elements([1, 2])
        s.store_context("key", "val")
        s.clear()
        assert s.get_elements() == []
        assert s.get_context("key") is None

    def test_session_expired(self):
        s = SessionState("test-6", ttl_seconds=0)
        time.sleep(0.01)
        assert s.is_expired() is True

    def test_session_not_expired(self):
        s = SessionState("test-7", ttl_seconds=3600)
        assert s.is_expired() is False

    def test_session_to_prompt_snippet_empty(self):
        s = SessionState("test-8")
        assert s.to_prompt_snippet() == ""

    def test_session_to_prompt_snippet(self):
        s = SessionState("test-9")
        s.set_last_request("найди двери без марки")
        s.store_elements([123, 456, 789], "doors_without_mark")
        snippet = s.to_prompt_snippet()
        assert "найди двери без марки" in snippet
        assert "doors_without_mark" in snippet
        assert "3 шт." in snippet

    def test_session_to_prompt_snippet_large(self):
        s = SessionState("test-10")
        s.store_elements(list(range(100)), "big_set")
        snippet = s.to_prompt_snippet()
        assert "всего 100" in snippet

    def test_session_elements_converted_to_int(self):
        s = SessionState("test-11")
        s.store_elements(["100", "200"], "converted")
        result = s.get_elements("converted")
        assert result == [100, 200]
        assert all(isinstance(x, int) for x in result)


# ── SessionManager Tests ────────────────────────────────────────────

class TestSessionManager:

    def setup_method(self):
        SessionManager._reset()

    def test_session_manager_singleton(self):
        m1 = SessionManager.get_instance()
        m2 = SessionManager.get_instance()
        assert m1 is m2

    def test_session_manager_get_or_create(self):
        m = SessionManager.get_instance()
        s1 = m.get_or_create("sess-1")
        s2 = m.get_or_create("sess-1")
        assert s1 is s2

    def test_session_manager_different_sessions(self):
        m = SessionManager.get_instance()
        s1 = m.get_or_create("a")
        s2 = m.get_or_create("b")
        assert s1 is not s2

    def test_session_cleanup(self):
        m = SessionManager.get_instance()
        # Create an expired session
        s = SessionState("expired", ttl_seconds=0)
        time.sleep(0.01)
        m._sessions["expired"] = s
        # Also a fresh one
        m.get_or_create("fresh")
        removed = m.cleanup_expired()
        assert removed == 1
        assert "expired" not in m._sessions
        assert "fresh" in m._sessions

    def test_session_manager_replaces_expired(self):
        m = SessionManager.get_instance()
        s_old = SessionState("reuse", ttl_seconds=0)
        time.sleep(0.01)
        m._sessions["reuse"] = s_old
        s_new = m.get_or_create("reuse")
        assert s_new is not s_old


# ── AuditLog Tests ──────────────────────────────────────────────────

class TestAuditLog:

    def test_audit_log_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=tmpdir)
            log.log_execution(
                session_id="s1",
                user_request="покажи стены",
                intent_type="read",
                code_executed="walls = FilteredElementCollector(doc).OfClass(Wall).ToElements()",
                result_status="success",
                retries=0,
                duration_ms=150.5,
                model_used="google/gemini-3-flash-preview",
            )

            # Check file was created
            files = os.listdir(tmpdir)
            assert len(files) == 1
            assert files[0].startswith("audit_")
            assert files[0].endswith(".jsonl")

            # Check content
            with open(os.path.join(tmpdir, files[0]), "r", encoding="utf-8") as f:
                line = f.readline()
                record = json.loads(line)

            assert record["session_id"] == "s1"
            assert record["request"] == "покажи стены"
            assert record["intent"] == "read"
            assert record["status"] == "success"
            assert record["retries"] == 0
            assert record["duration_ms"] == 150.5
            assert record["model"] == "google/gemini-3-flash-preview"
            assert len(record["code_hash"]) == 8
            assert "error" not in record

    def test_audit_log_with_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=tmpdir)
            log.log_execution(
                session_id="s2",
                user_request="удали всё",
                intent_type="dangerous",
                code_executed="",
                result_status="error",
                retries=2,
                duration_ms=3000,
                error="Permission denied",
            )
            files = os.listdir(tmpdir)
            with open(os.path.join(tmpdir, files[0]), "r", encoding="utf-8") as f:
                record = json.loads(f.readline())
            assert record["error"] == "Permission denied"
            assert record["code_hash"] == ""

    def test_audit_log_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=tmpdir)

            # Write several records
            for i in range(5):
                log.log_execution(
                    session_id="s1",
                    user_request="req {}".format(i),
                    intent_type="read" if i < 3 else "write",
                    code_executed="code_{}".format(i),
                    result_status="success" if i < 4 else "error",
                    retries=0 if i < 3 else 1,
                    duration_ms=100 + i * 50,
                    model_used="google/gemini-3-flash-preview",
                )

            stats = log.get_stats(days=1)
            assert stats["total"] == 5
            assert stats["success"] == 4
            assert stats["error"] == 1
            assert stats["by_intent"]["read"] == 3
            assert stats["by_intent"]["write"] == 2
            assert stats["avg_retries"] > 0

    def test_audit_log_stats_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log = AuditLog(log_dir=tmpdir)
            stats = log.get_stats(days=7)
            assert stats["total"] == 0
            assert stats["avg_retries"] == 0.0

    def test_audit_log_code_hash(self):
        h = AuditLog._code_hash("print('hello')")
        assert len(h) == 8
        assert AuditLog._code_hash("") == ""


# ── ModelRouter Tests ───────────────────────────────────────────────

class TestModelRouter:

    def setup_method(self):
        self.router = ModelRouter()

    def test_model_router_dangerous_uses_smart(self):
        model = self.router.route("удали все стены", "dangerous", 500)
        assert model == ModelRouter.MODELS["smart"]

    def test_model_router_large_context_uses_smart(self):
        model = self.router.route("покажи стены", "read", 9000)
        assert model == ModelRouter.MODELS["smart"]

    def test_model_router_long_request_uses_smart(self):
        long_req = "x" * 250
        model = self.router.route(long_req, "write", 500)
        assert model == ModelRouter.MODELS["smart"]

    def test_model_router_read_uses_fast(self):
        model = self.router.route("покажи стены", "read", 500)
        assert model == ModelRouter.MODELS["fast"]

    def test_model_router_default_fast(self):
        model = self.router.route("создай стену", "write", 500)
        assert model == ModelRouter.MODELS["fast"]

    def test_model_router_cost_estimate(self):
        cost = self.router.estimate_cost("google/gemini-3-flash-preview", 1000, 500)
        assert isinstance(cost, float)
        assert cost > 0
        assert cost < 0.01  # Should be very cheap

    def test_model_router_cost_estimate_smart(self):
        cost_fast = self.router.estimate_cost("google/gemini-3-flash-preview", 1000, 500)
        cost_smart = self.router.estimate_cost("anthropic/claude-sonnet-4-6", 1000, 500)
        assert cost_smart > cost_fast

    def test_model_router_cost_unknown_model(self):
        cost = self.router.estimate_cost("unknown/model", 1000, 500)
        assert isinstance(cost, float)
        assert cost > 0


# ── Phase 3 Additional Tests ────────────────────────────────────────

class TestPhase3Fixes:
    """Tests verifying Phase 3 bug fixes."""

    def test_confirm_dangerous_executes(self):
        """executor.execute(..., intent_type='dangerous', confirm=True) → not needs_confirmation."""
        executor = TransactionExecutor()
        # Provide a mock DB with Transaction that records calls
        mock_db = MagicMock()
        mock_transaction = MagicMock()
        mock_transaction.HasStarted.return_value = False
        mock_db.Transaction.return_value = mock_transaction

        namespace = {"DB": mock_db, "__captured_output__": []}
        code = "__result__ = {'summary': 'done', 'count': 1}"
        doc = MagicMock()

        result = executor.execute(code, doc, None, namespace, intent_type="dangerous", confirm=True)
        assert result["status"] != "needs_confirmation", (
            "confirm=True should bypass confirmation, got status: {}".format(result["status"])
        )

    def test_prompt_snippet_no_truncation(self):
        """to_prompt_snippet() with 15 IDs should produce clean '...' without truncated bracket."""
        s = SessionState("test-trunc")
        ids = list(range(15))  # 15 elements → triggers the > 10 branch
        s.store_elements(ids, "walls")
        snippet = s.to_prompt_snippet()
        # The old bug: str(ids[:10])[:-1] would produce '[0, 1, 2, ..., 9'  (missing closing bracket)
        # The fix:    str(ids[:10])        produces  '[0, 1, 2, ..., 9]'
        # Verify the closing bracket of the 10-element list is preserved
        assert "[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]..." in snippet, (
            "Expected properly closed list in snippet, got: {}".format(snippet)
        )
        assert "всего 15" in snippet


# ── Pipeline Integration Tests (mocked) ────────────────────────────

class TestPipelinePhase3:

    def _make_pipeline(self, tmpdir):
        """Create a pipeline with mocked LLM calls."""
        p = ExecuteV2Pipeline(openrouter_key="test-key", log_dir=tmpdir)
        return p

    def _mock_revit(self):
        """Create mock Revit objects."""
        doc = MagicMock()
        uidoc = MagicMock()
        DB = MagicMock()
        revit_mod = MagicMock()
        return doc, uidoc, DB, revit_mod

    @patch.object(ExecuteV2Pipeline, '_execute_pipeline')
    def test_pipeline_with_session(self, mock_exec):
        """Pipeline stores session data when session_id is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            SessionManager._reset()
            pipeline = self._make_pipeline(tmpdir)
            doc, uidoc, DB, revit_mod = self._mock_revit()

            mock_exec.return_value = {
                "status": "success",
                "response": "Done",
                "intent": {"intent_type": "read", "confidence": 0.9},
                "retries": 0,
                "code_executed": "x = 1",
                "raw_result": {"__result__": [100, 200], "output": "ok"},
                "model_used": "google/gemini-3-flash-preview",
            }

            result = pipeline.run(
                user_request="покажи стены",
                doc=doc, uidoc=uidoc, DB=DB, revit=revit_mod,
                session_id="test-session",
            )

            assert result["session_id"] == "test-session"
            assert result["model_used"] == "google/gemini-3-flash-preview"
            assert "duration_ms" in result

            # Check session has stored elements
            session = pipeline.session_manager.get_or_create("test-session")
            assert session.get_elements() == [100, 200]

    @patch.object(ExecuteV2Pipeline, '_execute_pipeline')
    def test_pipeline_audit_called(self, mock_exec):
        """Pipeline writes to audit log after execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            SessionManager._reset()
            pipeline = self._make_pipeline(tmpdir)
            doc, uidoc, DB, revit_mod = self._mock_revit()

            mock_exec.return_value = {
                "status": "success",
                "response": "Done",
                "intent": {"intent_type": "read", "confidence": 0.9},
                "retries": 0,
                "code_executed": "x = 1",
                "raw_result": {"output": "ok"},
                "model_used": "google/gemini-3-flash-preview",
            }

            pipeline.run(
                user_request="покажи стены",
                doc=doc, uidoc=uidoc, DB=DB, revit=revit_mod,
            )

            # Check audit log file exists and has a record
            files = [f for f in os.listdir(tmpdir) if f.endswith(".jsonl")]
            assert len(files) == 1
            with open(os.path.join(tmpdir, files[0]), "r", encoding="utf-8") as f:
                record = json.loads(f.readline())
            assert record["request"] == "покажи стены"
            assert record["status"] == "success"

    @patch.object(ExecuteV2Pipeline, '_execute_pipeline')
    def test_pipeline_without_session(self, mock_exec):
        """Pipeline works fine without session_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            SessionManager._reset()
            pipeline = self._make_pipeline(tmpdir)
            doc, uidoc, DB, revit_mod = self._mock_revit()

            mock_exec.return_value = {
                "status": "success",
                "response": "Done",
                "intent": {"intent_type": "read", "confidence": 0.9},
                "retries": 0,
                "code_executed": "x = 1",
                "raw_result": {"output": "ok"},
                "model_used": "google/gemini-3-flash-preview",
            }

            result = pipeline.run(
                user_request="test",
                doc=doc, uidoc=uidoc, DB=DB, revit=revit_mod,
            )
            assert result["session_id"] == ""

    @patch.object(ExecuteV2Pipeline, '_execute_pipeline')
    def test_pipeline_audit_on_error(self, mock_exec):
        """Pipeline logs to audit even on exception."""
        with tempfile.TemporaryDirectory() as tmpdir:
            SessionManager._reset()
            pipeline = self._make_pipeline(tmpdir)
            doc, uidoc, DB, revit_mod = self._mock_revit()

            mock_exec.side_effect = RuntimeError("boom")

            with pytest.raises(RuntimeError):
                pipeline.run(
                    user_request="fail",
                    doc=doc, uidoc=uidoc, DB=DB, revit=revit_mod,
                )

            files = [f for f in os.listdir(tmpdir) if f.endswith(".jsonl")]
            assert len(files) == 1
            with open(os.path.join(tmpdir, files[0]), "r", encoding="utf-8") as f:
                record = json.loads(f.readline())
            assert record["status"] == "error"
            assert record["error"] == "boom"
