"""
Phase 2 unit tests — IntentClassifier, ResultFormatter, CodeGenerator, Pipeline.
Pure Python 3, no Revit dependency. All LLM calls are mocked.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock

# Add parent paths so imports work without package install
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from revit_mcp.execute_v2.intent_classifier import IntentClassifier, IntentType
from revit_mcp.execute_v2.result_formatter import ResultFormatter
from revit_mcp.execute_v2.code_generator import CodeGenerator
from revit_mcp.execute_v2.context_builder import ContextBuilder
from revit_mcp.execute_v2.retry_loop import RetryLoop
from revit_mcp.execute_v2.pipeline import ExecuteV2Pipeline
from revit_mcp.execute_v2.sandbox_validator import SandboxValidator
from revit_mcp.execute_v2.model_router import ModelRouter
from revit_mcp.execute_v2.multi_step import detect_multi_step


# ── IntentClassifier Tests ──────────────────────────────────────────

class TestIntentClassifier:
    def setup_method(self):
        self.c = IntentClassifier()

    # --- DANGEROUS ---
    def test_intent_dangerous_ru_delete(self):
        result = self.c.classify("удали все стены на этаже")
        assert result["intent_type"] == IntentType.DANGEROUS
        assert "удали" in result["detected_keywords"]

    def test_intent_dangerous_en_delete(self):
        result = self.c.classify("delete all walls from level 1")
        assert result["intent_type"] == IntentType.DANGEROUS
        assert "delete" in result["detected_keywords"]

    def test_intent_dangerous_purge(self):
        result = self.c.classify("purge unused families")
        assert result["intent_type"] == IntentType.DANGEROUS

    def test_intent_dangerous_ru_destroy(self):
        result = self.c.classify("снеси перегородки в зоне А")
        assert result["intent_type"] == IntentType.DANGEROUS

    def test_intent_dangerous_wipe(self):
        result = self.c.classify("wipe all annotations")
        assert result["intent_type"] == IntentType.DANGEROUS

    # --- WRITE ---
    def test_intent_write_ru_rename(self):
        result = self.c.classify("переименуй все двери на 1 этаже")
        assert result["intent_type"] == IntentType.WRITE
        assert "переименуй" in result["detected_keywords"]

    def test_intent_write_en_create(self):
        result = self.c.classify("create a new level at elevation 10m")
        assert result["intent_type"] == IntentType.WRITE
        assert "create" in result["detected_keywords"]

    def test_intent_write_ru_set(self):
        result = self.c.classify("установи параметр Марка = A1 для стен")
        assert result["intent_type"] == IntentType.WRITE

    def test_intent_write_en_modify(self):
        result = self.c.classify("modify wall thickness to 300mm")
        assert result["intent_type"] == IntentType.WRITE

    def test_intent_write_ru_add(self):
        result = self.c.classify("добавь окна в стену")
        assert result["intent_type"] == IntentType.WRITE

    # --- VIEW_OP ---
    def test_intent_viewop_ru_isolate(self):
        result = self.c.classify("изолируй стены на виде")
        assert result["intent_type"] == IntentType.VIEW_OP

    def test_intent_viewop_en_zoom(self):
        result = self.c.classify("zoom to selected elements")
        assert result["intent_type"] == IntentType.VIEW_OP

    def test_intent_viewop_ru_hide(self):
        result = self.c.classify("скрой все трубы на текущем виде")
        assert result["intent_type"] == IntentType.VIEW_OP

    def test_intent_viewop_en_select(self):
        result = self.c.classify("select all doors on level 1")
        assert result["intent_type"] == IntentType.VIEW_OP

    def test_intent_viewop_en_navigate(self):
        result = self.c.classify("navigate to section view A-A")
        assert result["intent_type"] == IntentType.VIEW_OP

    # --- READ ---
    def test_intent_read_ru_count(self):
        result = self.c.classify("сколько стен в проекте")
        assert result["intent_type"] == IntentType.READ
        assert result["confidence"] >= 0.7

    def test_intent_read_en_list(self):
        result = self.c.classify("list all levels in the project")
        assert result["intent_type"] == IntentType.READ

    def test_intent_read_ru_find(self):
        result = self.c.classify("найди все помещения без номера")
        assert result["intent_type"] == IntentType.READ

    def test_intent_read_en_what(self):
        result = self.c.classify("what is the area of room 101")
        assert result["intent_type"] == IntentType.READ

    def test_intent_read_default(self):
        """Unknown request defaults to READ with low confidence."""
        result = self.c.classify("привет как дела")
        assert result["intent_type"] == IntentType.READ
        assert result["confidence"] == 0.5

    def test_intent_empty_request(self):
        result = self.c.classify("")
        assert result["intent_type"] == IntentType.READ
        assert result["confidence"] == 0.5

    # --- Priority tests ---
    def test_dangerous_beats_write(self):
        """'удали' (dangerous) should win over 'создай' (write)."""
        result = self.c.classify("удали и создай стены заново")
        assert result["intent_type"] == IntentType.DANGEROUS

    def test_write_beats_viewop(self):
        """'переименуй' (write) should win over 'покажи' (read)."""
        result = self.c.classify("переименуй и покажи результат")
        assert result["intent_type"] == IntentType.WRITE


# ── ResultFormatter Tests ───────────────────────────────────────────

class TestResultFormatter:
    def setup_method(self):
        self.f = ResultFormatter()

    def test_formatter_success_with_result(self):
        result = {
            "status": "success",
            "result": {"summary": "Найдено 23 стены", "count": 23, "details": []},
            "output": "",
        }
        text = self.f.format(result, "найди стены", "read")
        assert "Найдено 23 стены" in text
        assert "📋" in text

    def test_formatter_success_write(self):
        result = {
            "status": "success",
            "result": {"summary": "Переименовано 47 дверей", "count": 47},
            "output": "",
        }
        text = self.f.format(result, "переименуй двери", "write")
        assert "Переименовано 47 дверей" in text
        assert "✅" in text

    def test_formatter_error(self):
        result = {
            "status": "error",
            "error_type": "AttributeError",
            "error_message": "объект не имеет атрибута 'Name'",
            "output": "traceback...",
        }
        text = self.f.format(result, "покажи имена", "read")
        assert "❌" in text
        assert "AttributeError" in text

    def test_formatter_confirmation(self):
        result = {
            "status": "needs_confirmation",
            "description": "удаление 150 элементов",
            "preview": "code here...",
        }
        text = self.f.format(result, "удали стены", "dangerous")
        assert "⚠️" in text
        assert "подтверждения" in text.lower()

    def test_formatter_rejected(self):
        result = {
            "status": "rejected",
            "reason": "Import of 'os' module is blocked",
        }
        text = self.f.format(result, "...", "read")
        assert "🚫" in text
        assert "os" in text.lower()

    def test_formatter_success_with_details(self):
        result = {
            "status": "success",
            "result": {
                "summary": "Уровни проекта",
                "count": 3,
                "details": [
                    {"name": "Level 1", "elevation": 0.0},
                    {"name": "Level 2", "elevation": 3.0},
                    {"name": "Level 3", "elevation": 6.0},
                ],
            },
        }
        text = self.f.format(result, "покажи уровни", "read")
        assert "Level 1" in text
        assert "Level 2" in text

    def test_formatter_no_result_uses_output(self):
        result = {
            "status": "success",
            "result": None,
            "output": "Printed output here",
        }
        text = self.f.format(result, "test", "read")
        assert "Printed output here" in text

    def test_formatter_unknown_status(self):
        result = {"status": "weird"}
        text = self.f.format(result, "test", "read")
        assert "weird" in text


# ── CodeGenerator._extract_code Tests ──────────────────────────────

class TestCodeExtractor:
    def test_extract_python_block(self):
        response = "Here's the code:\n```python\nx = 1\ny = 2\n```\nDone."
        result = CodeGenerator._extract_code(response)
        assert result == "x = 1\ny = 2"

    def test_extract_ironpython_block(self):
        response = "```ironpython\nwalls = DB.FilteredElementCollector(doc)\n```"
        result = CodeGenerator._extract_code(response)
        assert "FilteredElementCollector" in result

    def test_extract_generic_block(self):
        response = "Code:\n```\nresult = 42\n```"
        result = CodeGenerator._extract_code(response)
        assert result == "result = 42"

    def test_extract_no_block(self):
        response = "__result__ = {'count': 5}"
        result = CodeGenerator._extract_code(response)
        assert "__result__" in result

    def test_extract_empty(self):
        result = CodeGenerator._extract_code("")
        assert result == ""

    def test_extract_none(self):
        result = CodeGenerator._extract_code(None)
        assert result == ""

    def test_extract_multiple_blocks_takes_first(self):
        response = "```python\nfirst = 1\n```\nAnd also:\n```python\nsecond = 2\n```"
        result = CodeGenerator._extract_code(response)
        assert "first" in result


# ── ContextBuilder Tests ────────────────────────────────────────────

class TestContextBuilder:
    def test_cache_works(self):
        cb = ContextBuilder()
        mock_doc = MagicMock()
        mock_doc.ProjectInformation.Name = "Test Project"
        mock_doc.Application.VersionNumber = "2024"
        mock_doc.ActiveView.Name = "Floor Plan"
        mock_doc.ActiveView.ViewType = "FloorPlan"

        mock_uidoc = MagicMock()

        # First call
        ctx1 = cb.build(mock_doc, mock_uidoc)
        assert ctx1["project_name"] == "Test Project"

        # Modify mock — but cache should return old value
        mock_doc.ProjectInformation.Name = "Changed"
        ctx2 = cb.build(mock_doc, mock_uidoc)
        assert ctx2["project_name"] == "Test Project"  # cached

    def test_cache_invalidation(self):
        cb = ContextBuilder()
        mock_doc = MagicMock()
        mock_doc.ProjectInformation.Name = "Test"
        mock_doc.Application.VersionNumber = "2024"
        mock_doc.ActiveView.Name = "View1"
        mock_doc.ActiveView.ViewType = "FloorPlan"
        mock_uidoc = MagicMock()

        cb.build(mock_doc, mock_uidoc)
        cb.invalidate_cache()
        mock_doc.ProjectInformation.Name = "New Name"
        ctx = cb.build(mock_doc, mock_uidoc)
        assert ctx["project_name"] == "New Name"

    def test_context_code_string(self):
        cb = ContextBuilder()
        code = cb.get_context_code()
        assert "__result__" in code
        assert "context" in code
        # Verify no f-strings (IronPython 2.7 compat)
        assert "f'" not in code
        assert 'f"' not in code

    def test_build_from_result(self):
        cb = ContextBuilder()
        fake_result = {"project_name": "External", "levels": []}
        out = cb.build_from_result(fake_result)
        assert out["project_name"] == "External"
        # Should be cached now
        assert cb._cache is not None


# ── Pipeline Integration Tests (mocked LLM) ────────────────────────

class TestPipeline:
    def _make_mocks(self):
        doc = MagicMock()
        doc.ProjectInformation.Name = "Test"
        doc.Application.VersionNumber = "2024"
        doc.ActiveView.Name = "Plan"
        doc.ActiveView.ViewType = "FloorPlan"
        uidoc = MagicMock()
        DB = MagicMock()
        revit = MagicMock()
        return doc, uidoc, DB, revit

    def test_pipeline_validation_rejected(self):
        """Pipeline should reject code with 'import os'."""
        doc, uidoc, DB, revit = self._make_mocks()
        pipeline = ExecuteV2Pipeline(openrouter_key="fake-key")

        # Mock the generator to return dangerous code
        pipeline.generator.generate = MagicMock(return_value={
            "code": "import os\nos.listdir('.')\n__result__ = {'summary': 'hacked'}",
            "model_used": "test",
            "tokens": 10,
        })

        result = pipeline.run("покажи файлы", doc, uidoc, DB, revit)
        assert result["status"] == "rejected"
        assert "🚫" in result["response"]

    def test_pipeline_success_read(self):
        """Pipeline should succeed with safe read code."""
        doc, uidoc, DB, revit = self._make_mocks()
        pipeline = ExecuteV2Pipeline(openrouter_key="fake-key")

        safe_code = "__result__ = {'summary': 'Found 10 walls', 'count': 10}"
        pipeline.generator.generate = MagicMock(return_value={
            "code": safe_code,
            "model_used": "test",
            "tokens": 10,
        })

        result = pipeline.run("сколько стен в проекте", doc, uidoc, DB, revit)
        assert result["status"] == "success"
        assert "Found 10 walls" in result["response"]
        assert result["intent"]["intent_type"] == "read"

    def test_pipeline_empty_code(self):
        """Pipeline should handle empty code from LLM."""
        doc, uidoc, DB, revit = self._make_mocks()
        pipeline = ExecuteV2Pipeline(openrouter_key="fake-key")

        pipeline.generator.generate = MagicMock(return_value={
            "code": "",
            "model_used": "test",
            "tokens": 0,
        })

        result = pipeline.run("что-то", doc, uidoc, DB, revit)
        assert result["status"] == "error"

    def test_pipeline_dangerous_intent(self):
        """Dangerous intent should request confirmation (not execute)."""
        doc, uidoc, DB, revit = self._make_mocks()
        pipeline = ExecuteV2Pipeline(openrouter_key="fake-key")

        pipeline.generator.generate = MagicMock(return_value={
            "code": "# delete stuff\n__result__ = {'summary': 'deleted'}",
            "model_used": "test",
            "tokens": 10,
        })

        result = pipeline.run("удали все стены", doc, uidoc, DB, revit)
        assert result["intent"]["intent_type"] == "dangerous"
        assert result["status"] == "needs_confirmation"

    def test_pipeline_generation_error(self):
        """Pipeline should handle LLM generation exceptions."""
        doc, uidoc, DB, revit = self._make_mocks()
        pipeline = ExecuteV2Pipeline(openrouter_key="fake-key")

        pipeline.generator.generate = MagicMock(side_effect=Exception("API down"))

        result = pipeline.run("что-то сделай", doc, uidoc, DB, revit)
        assert result["status"] == "error"
        assert "API down" in result["response"]


# ── RetryLoop Tests ─────────────────────────────────────────────────

class TestRetryLoop:
    def test_retry_success_first_try(self):
        """No retries needed if first execution succeeds."""
        generator = MagicMock()
        validator = SandboxValidator()
        executor = MagicMock()
        executor.execute.return_value = {
            "status": "success",
            "output": "",
            "result": {"summary": "ok", "count": 1},
        }

        loop = RetryLoop(generator, validator, executor, max_retries=2)
        result = loop.run("x = 1", MagicMock(), MagicMock(), MagicMock(), MagicMock(), "read")
        assert result["status"] == "success"
        assert result["retries"] == 0

    def test_retry_fixes_on_second_try(self):
        """Retry should succeed after fix."""
        generator = MagicMock()
        generator.fix.return_value = {"code": "__result__ = {'summary': 'fixed', 'count': 1}"}

        validator = SandboxValidator()
        executor = MagicMock()
        # First retry: success
        executor.execute.return_value = {
            "status": "success", "output": "", "result": {"summary": "fixed"},
        }

        loop = RetryLoop(generator, validator, executor, max_retries=2)
        initial_error = {"status": "error", "output": "err", "error_type": "NameError", "error_message": "x"}
        result = loop.run("bad code", MagicMock(), MagicMock(), MagicMock(), MagicMock(), "read",
                         initial_result=initial_error)
        assert result["retries"] == 1
        assert result["status"] == "success"
        assert generator.fix.call_count == 1


# ── Phase 2 Fixes Verification Tests ───────────────────────────────

class TestPhase2Fixes:
    """Tests verifying Phase 2 bug fixes."""

    def test_model_router_context_threshold(self):
        """Context size 5000 should route to fast model (threshold raised to 8000)."""
        router = ModelRouter()
        # 5000 chars — below new 8000 threshold → fast model
        result_5k = router.route("test request", "read", 5000)
        assert result_5k == router.MODELS["fast"], (
            "Expected fast model for context_size=5000, got {}".format(result_5k)
        )
        # 9000 chars — above 8000 threshold → smart model
        result_9k = router.route("test request", "read", 9000)
        assert result_9k == router.MODELS["smart"], (
            "Expected smart model for context_size=9000, got {}".format(result_9k)
        )

    def test_retry_loop_passes_context(self):
        """RetryLoop should pass context kwarg to generator.fix()."""
        generator = MagicMock()
        generator.fix.return_value = {"code": "__result__ = {'summary': 'ok'}"}

        validator = SandboxValidator()
        executor = MagicMock()
        executor.execute.return_value = {
            "status": "success", "output": "", "result": {"summary": "ok"},
        }

        loop = RetryLoop(generator, validator, executor, max_retries=2)
        initial_error = {
            "status": "error", "output": "err",
            "error_type": "NameError", "error_message": "x",
        }
        test_context = {"project_name": "Test", "levels": []}
        loop.run(
            "bad code", MagicMock(), MagicMock(), MagicMock(), MagicMock(),
            "read", initial_result=initial_error, context=test_context,
        )
        # Verify fix was called with context keyword argument
        assert generator.fix.call_count == 1
        _, kwargs = generator.fix.call_args
        assert "context" in kwargs, "generator.fix() was not called with context kwarg"
        assert kwargs["context"] == test_context

    def test_multi_step_detection(self):
        """Multi-step detection should catch Russian sequential markers."""
        assert detect_multi_step("найди все стены потом переименуй их") is True
        assert detect_multi_step("найди все стены") is False
        assert detect_multi_step("сначала посчитай стены, затем покажи результат") is True
        assert detect_multi_step("first find walls then rename them") is True

    def test_code_generator_default_model_synced(self):
        """DEFAULT_MODEL should match ModelRouter MODELS['fast']."""
        router = ModelRouter()
        gen = CodeGenerator(api_key="fake")
        assert gen.DEFAULT_MODEL == router.MODELS["fast"], (
            "CodeGenerator.DEFAULT_MODEL ({}) != ModelRouter.MODELS['fast'] ({})".format(
                gen.DEFAULT_MODEL, router.MODELS["fast"]
            )
        )

    def test_model_router_threshold_8000(self):
        """context_size=5000 should route to fast model, not smart (threshold=8000)."""
        router = ModelRouter()
        assert router.route("simple request", "read", 5000) == router.MODELS["fast"]
        assert router.route("simple request", "read", 8001) == router.MODELS["smart"]

    def test_default_model_is_gemini3(self):
        """CodeGenerator.DEFAULT_MODEL must contain 'gemini-3'."""
        assert "gemini-3" in CodeGenerator.DEFAULT_MODEL, (
            "Expected 'gemini-3' in DEFAULT_MODEL, got: {}".format(CodeGenerator.DEFAULT_MODEL)
        )

    def test_fix_accepts_context(self):
        """generator.fix(code, error, context={...}) should not raise."""
        gen = CodeGenerator(api_key="fake")
        # Mock _call_llm to avoid real API call
        gen._call_llm = MagicMock(return_value={"content": "```python\n__result__ = {}\n```", "tokens": 5})
        error = {"error_type": "NameError", "error_message": "x not defined", "output": ""}
        result = gen.fix("x = broken", error, context={"levels": [], "project_name": "Test"})
        assert "code" in result
        # Verify context was included in the LLM call
        call_args = gen._call_llm.call_args
        user_msg = call_args[1].get("user_message", "") or call_args[0][2] if len(call_args[0]) > 2 else ""
        assert "levels" in str(call_args), "Context should be passed to LLM in fix prompt"

    def test_pipeline_singleton(self):
        """Two calls to _get_pipeline() should return the same instance."""
        # Mock pyrevit so route module can be imported in test env
        sys.modules.setdefault("pyrevit", MagicMock())
        sys.modules.setdefault("pyrevit.routes", MagicMock())
        import revit_mcp.execute_v2_route as route_mod
        # Reset singleton and mock the Pipeline constructor
        route_mod._pipeline_instance = None
        mock_pipeline = MagicMock()
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("revit_mcp.execute_v2.ExecuteV2Pipeline", return_value=mock_pipeline):
                first = route_mod._get_pipeline()
                second = route_mod._get_pipeline()
                assert first is second, "Singleton should return same instance on repeated calls"
        # Cleanup
        route_mod._pipeline_instance = None
