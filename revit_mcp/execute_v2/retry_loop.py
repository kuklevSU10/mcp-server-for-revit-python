"""
Retry Loop — handles code fix + re-execution attempts.

Separated from pipeline for testability and reuse.
"""

import logging
import time
from typing import Any, Dict

from .sandbox_validator import SandboxValidator
from .timeout_instrumenter import instrument_loops
from .safe_namespace import build_safe_namespace
from .transaction_executor import TransactionExecutor


logger = logging.getLogger("kukai.execute_v2.retry")


class RetryLoop:
    """
    Retry loop for code execution with LLM-based error fixing.
    
    On each retry:
        1. Ask CodeGenerator to fix the code
        2. Re-validate with SandboxValidator
        3. Re-instrument loops
        4. Re-execute
    """

    def __init__(self, generator, validator=None, executor=None, max_retries=3):
        """
        Args:
            generator: CodeGenerator instance (must have .fix() method).
            validator: SandboxValidator instance (default: new instance).
            executor: TransactionExecutor instance (default: new instance).
            max_retries: Maximum number of fix attempts.
        """
        self.generator = generator
        self.validator = validator or SandboxValidator()
        self.executor = executor or TransactionExecutor()
        self.max_retries = max_retries

    def run(
        self,
        initial_code: str,
        doc: Any,
        uidoc: Any,
        DB: Any,
        revit: Any,
        intent_type: str,
        initial_result: Dict = None,
        context: Dict = None,
        confirm: bool = False,
    ) -> Dict:
        """
        Execute code with retry on errors.

        Args:
            initial_code: First version of code to execute.
            doc: Revit Document.
            uidoc: Revit UIDocument.
            DB: Autodesk.Revit.DB module.
            revit: pyRevit revit module.
            intent_type: Intent classification string.
            initial_result: If provided, skip first execution (already failed).

        Returns:
            {
                "status": "success" | "error",
                "result": {...},
                "code": "final code",
                "retries": N,
                "attempts": [{"code": "...", "result": {...}}, ...],
            }
        """
        attempts = []
        code = initial_code
        result = initial_result

        # First execution (if not already provided)
        if result is None:
            result = self._execute_once(code, doc, uidoc, DB, revit, intent_type, confirm=confirm)
            attempts.append({"code": code, "result": result})

            if result["status"] != "error":
                return self._build_output(result, code, 0, attempts)
        else:
            attempts.append({"code": code, "result": result})

        # Retry loop
        retries = 0
        while result["status"] == "error" and retries < self.max_retries:
            retries += 1
            logger.info("Retry attempt %d/%d", retries, self.max_retries)

            # Exponential backoff: sleep for 1s, then 2s, etc. before asking for fix
            backoff_time = 1.0 * (2 ** (retries - 1))
            time.sleep(backoff_time)

            # Ask LLM to fix (enrich result with extracted hints)
            try:
                hints = self._extract_error_hints(result)
                enriched_result = dict(result)
                if hints:
                    existing_hints = enriched_result.get("hints", [])
                    if isinstance(existing_hints, list):
                        enriched_result["hints"] = existing_hints + hints
                    else:
                        enriched_result["hints"] = hints
                    logger.debug("Added %d hints for retry: %s", len(hints), hints)
                fixed = self.generator.fix(code, enriched_result, context=context)
                code = fixed.get("code", "")
            except Exception as e:
                logger.error("Code fix failed: %s", e)
                break

            if not code:
                logger.warning("LLM returned empty fix")
                break

            # Re-validate
            validation = self.validator.validate(code)
            if not validation["valid"]:
                logger.warning("Fixed code failed validation: %s", validation.get("reason"))
                result = {
                    "status": "error",
                    "output": "Fixed code failed validation: {}".format(validation.get("reason", "")),
                    "error_type": "ValidationError",
                    "error_message": validation.get("reason", ""),
                }
                attempts.append({"code": code, "result": result})
                break

            # Re-instrument and execute
            result = self._execute_once(code, doc, uidoc, DB, revit, intent_type, confirm=confirm)
            attempts.append({"code": code, "result": result})

            if result["status"] != "error":
                break

        return self._build_output(result, code, retries, attempts)

    def _execute_once(self, code, doc, uidoc, DB, revit, intent_type, confirm=False):
        """Instrument and execute code once."""
        try:
            instrumented = instrument_loops(code)
        except SyntaxError as e:
            return {
                "status": "error",
                "output": "SyntaxError in code: {}".format(str(e)),
                "error_type": "SyntaxError",
                "error_message": str(e),
            }

        namespace = build_safe_namespace(doc, uidoc, DB, revit, [])
        return self.executor.execute(instrumented, doc, uidoc, namespace, intent_type, confirm=confirm)

    def _extract_error_hints(self, result: Dict) -> list:
        """Extract actionable hints from an error result for better LLM fix prompts."""
        hints = []
        err_type = result.get("error_type", "")
        err_msg = result.get("error_message", "") or result.get("output", "")

        if "NullReference" in err_type or "NoneType" in err_msg:
            hints.append("Check for None before accessing attributes")
        if "AttributeError" in err_type and ".Name" in err_msg:
            hints.append("Use getattr(elem, 'Name', '') instead of elem.Name")
        if "Transaction" in err_msg or "InvalidOperation" in err_type:
            hints.append("Do not create Transaction manually — system handles it")
        if "RoomFilter" in err_msg or "OST_Rooms" in err_msg:
            hints.append("For Rooms use WherePasses(RoomFilter()) not OfClass(Room)")
        if "f-string" in err_msg or "SyntaxError" in err_type:
            hints.append("No f-strings in IronPython 2.7 — use .format()")
        if "IntegerValue" in err_msg:
            hints.append("Use eid_value(eid) instead of eid.IntegerValue for Revit 2024+")
        if "iteration" in err_msg or "non-sequence" in err_msg:
            hints.append("Wrap .NET collections in list(): list(collector.ToElements())")
        if "__result__" not in (result.get("output") or ""):
            hints.append("Code must set __result__ = {'summary': ..., 'count': ...} at the end")

        return hints

    def _build_output(self, result, code, retries, attempts):
        """Build final output dict."""
        output = {
            "status": result.get("status", "error"),
            "result": result,
            "code": code,
            "retries": retries,
            "attempts": attempts,
        }
        if output["status"] == "error":
            output["error_hints"] = self._extract_error_hints(result)
        return output
