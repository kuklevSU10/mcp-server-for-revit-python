"""
Phase 1 unit tests — SandboxValidator and TimeoutInstrumenter.
Pure Python 3, no Revit dependency.
"""

import pytest
import sys
import os
import threading

# Add parent paths so imports work without package install
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from revit_mcp.execute_v2.sandbox_validator import SandboxValidator
from revit_mcp.execute_v2.timeout_instrumenter import instrument_loops
from revit_mcp.execute_v2.safe_namespace import build_safe_namespace, SAFE_BUILTINS_NAMES


# ── SandboxValidator Tests ──────────────────────────────────────────

class TestSandboxValidator:
    def setup_method(self):
        self.v = SandboxValidator()

    def test_blocks_os_import(self):
        result = self.v.validate("import os\nos.listdir('.')")
        assert result["valid"] is False
        assert "os" in result["reason"].lower()

    def test_blocks_os_from_import(self):
        result = self.v.validate("from os import path")
        assert result["valid"] is False

    def test_blocks_subprocess_import(self):
        result = self.v.validate("import subprocess")
        assert result["valid"] is False

    def test_blocks_sys_import(self):
        result = self.v.validate("import sys\nsys.exit()")
        assert result["valid"] is False

    def test_blocks_shutil_import(self):
        result = self.v.validate("import shutil")
        assert result["valid"] is False

    def test_blocks_system_io(self):
        result = self.v.validate('clr.AddReference("System")\nfrom System.IO import File')
        assert result["valid"] is False
        assert "System.IO" in result["blocked_pattern"]

    def test_blocks_system_net(self):
        result = self.v.validate("System.Net.WebClient()")
        assert result["valid"] is False

    def test_blocks_system_diagnostics(self):
        result = self.v.validate("System.Diagnostics.Process.Start('cmd')")
        assert result["valid"] is False

    def test_blocks_system_reflection(self):
        result = self.v.validate("System.Reflection.Assembly.Load('evil')")
        assert result["valid"] is False

    def test_blocks_dunder_import(self):
        result = self.v.validate("__import__('os')")
        assert result["valid"] is False

    def test_blocks_open(self):
        result = self.v.validate("f = open('secret.txt', 'r')")
        assert result["valid"] is False

    def test_blocks_file(self):
        result = self.v.validate("f = file('secret.txt')")
        assert result["valid"] is False

    def test_blocks_exec(self):
        result = self.v.validate("exec('import os')")
        assert result["valid"] is False

    def test_blocks_eval(self):
        result = self.v.validate("eval('1+1')")
        assert result["valid"] is False

    def test_blocks_doc_delete(self):
        result = self.v.validate("doc.Delete(element.Id)")
        assert result["valid"] is False
        assert "doc.Delete" in result["blocked_pattern"]

    def test_blocks_open_document_file(self):
        result = self.v.validate("Application.OpenDocumentFile(path)")
        assert result["valid"] is False

    def test_allows_safe_code(self):
        safe_code = """
walls = DB.FilteredElementCollector(doc).OfClass(DB.Wall).ToElements()
count = len(walls)
details = []
for w in walls:
    details.append({"id": w.Id.IntegerValue})
__result__ = {"summary": "Found {} walls".format(count), "count": count, "details": details}
"""
        result = self.v.validate(safe_code)
        assert result["valid"] is True

    def test_allows_revit_api_calls(self):
        code = """
levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
for lvl in levels:
    print(lvl.Name)
"""
        result = self.v.validate(code)
        assert result["valid"] is True

    def test_blocks_long_code(self):
        long_code = "x = 1\n" * 10001  # well over 50K chars
        result = self.v.validate(long_code)
        assert result["valid"] is False
        assert "length" in result["reason"].lower()


# ── TimeoutInstrumenter Tests ───────────────────────────────────────

class TestTimeoutInstrumenter:
    def test_instrument_for_loop(self):
        code = "for i in range(10):\n    print(i)\n"
        result = instrument_loops(code, max_iterations=1000)
        assert "_kukai_loop_cnt_" in result
        assert "RuntimeError" in result
        assert "1000" in result

    def test_instrument_while_loop(self):
        code = "x = 0\nwhile x < 10:\n    x += 1\n"
        result = instrument_loops(code, max_iterations=500)
        assert "_kukai_loop_cnt_" in result
        assert "500" in result

    def test_nested_loops(self):
        code = "for i in range(10):\n    for j in range(10):\n        pass\n"
        result = instrument_loops(code, max_iterations=100)
        # Should have 2 different counters
        assert result.count("_kukai_loop_cnt_") >= 4  # init + check for each loop

    def test_no_loops_unchanged(self):
        code = "x = 1\ny = 2\nz = x + y\n"
        result = instrument_loops(code)
        assert "_kukai_loop_cnt_" not in result

    def test_instrumented_code_runs(self):
        """Verify instrumented code actually executes correctly."""
        code = "result = []\nfor i in range(5):\n    result.append(i)\n"
        instrumented = instrument_loops(code, max_iterations=100)
        ns = {}
        exec(instrumented, ns)
        assert ns["result"] == [0, 1, 2, 3, 4]

    def test_instrumented_code_raises_on_limit(self):
        """Verify instrumented code raises RuntimeError when limit exceeded."""
        code = "x = 0\nwhile True:\n    x += 1\n"
        instrumented = instrument_loops(code, max_iterations=50)
        ns = {}
        with pytest.raises(RuntimeError, match="KUKAI: Loop limit exceeded"):
            exec(instrumented, ns)

    def test_syntax_error_propagates(self):
        """Bad syntax should raise SyntaxError."""
        with pytest.raises(SyntaxError):
            instrument_loops("def broken(:\n    pass\n")


# ── Phase 1 Fixes — New Tests ──────────────────────────────────────

class TestPhase1Fixes:
    """Tests for Phase 1 critical bug fixes."""

    def test_collect_output_works(self):
        """FIX 1: __captured_output__ exists in namespace and print() writes to it."""
        captured = []
        ns = build_safe_namespace(
            doc=None, uidoc=None, DB=None, revit=None,
            captured_output=captured,
        )
        assert "__captured_output__" in ns
        assert ns["__captured_output__"] is captured
        # Call print via builtins — should append to captured
        ns["__builtins__"]["print"]("hello", "world")
        assert len(captured) == 1
        assert "hello world" in captured[0]

    def test_setattr_not_in_builtins(self):
        """FIX 2: setattr and delattr must NOT be in SAFE_BUILTINS_NAMES."""
        assert "setattr" not in SAFE_BUILTINS_NAMES
        assert "delattr" not in SAFE_BUILTINS_NAMES

    def test_clr_addreference_blocked(self):
        """FIX 3: clr.AddReference() must be blocked."""
        v = SandboxValidator()
        result = v.validate("clr.AddReference('mscorlib')")
        assert result["valid"] is False
        assert "clr.AddReference" in result["blocked_pattern"]

    def test_validate_returns_all_errors(self):
        """FIX 4: validate() should return all_errors with multiple violations."""
        v = SandboxValidator()
        # Code with two violations: import os + exec()
        code = "import os\nexec('evil')"
        result = v.validate(code)
        assert result["valid"] is False
        assert "all_errors" in result
        assert len(result["all_errors"]) >= 2
        reasons = [e["reason"] for e in result["all_errors"]]
        assert any("os" in r.lower() for r in reasons)
        assert any("exec" in r.lower() for r in reasons)

    def test_counter_thread_safe(self):
        """FIX 5: instrument_loops from multiple threads should not collide."""
        results = {}
        errors = []

        def worker(thread_id):
            try:
                code = "for i in range(10):\n    pass\n"
                result = instrument_loops(code, max_iterations=1000)
                results[thread_id] = result
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, "Errors in threads: {}".format(errors)
        assert len(results) == 10
        # Each result should be valid instrumented code
        for tid, code in results.items():
            assert "_kukai_loop_cnt_" in code

    def test_json_in_namespace(self):
        """FIX 6: json, math, re, collections should be available in namespace."""
        import json
        import math
        import re
        import collections

        ns = build_safe_namespace(
            doc=None, uidoc=None, DB=None, revit=None,
            captured_output=[],
        )
        assert ns["json"] is json
        assert ns["math"] is math
        assert ns["re"] is re
        assert ns["collections"] is collections
