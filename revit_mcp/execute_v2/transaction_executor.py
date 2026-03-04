"""
Transaction Executor — auto-wraps IronPython code in Revit Transactions.

This module generates wrapper code that runs INSIDE Revit (IronPython 2.7 compatible).
The execute() method itself runs on Python 3 but produces IronPython-safe code strings.
"""

import traceback
from typing import Any, Dict, List


class TransactionExecutor:
    """
    Executes IronPython code with automatic Transaction management based on intent.

    Intent types:
        - read: No transaction, just exec
        - write: Auto-wrap in DB.Transaction
        - view_op: No transaction (UI operations)
        - dangerous: TransactionGroup + confirmation required
    """

    VALID_INTENTS = {"read", "write", "view_op", "dangerous"}

    def execute(
        self,
        code: str,
        doc: Any,
        uidoc: Any,
        namespace: Dict[str, Any],
        intent_type: str = "read",
        description: str = "AI Operation",
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute code with appropriate transaction wrapping.

        Args:
            code: IronPython code string to execute
            doc: Revit Document
            uidoc: Revit UIDocument
            namespace: Safe namespace dict (from SafeNamespace)
            intent_type: One of 'read', 'write', 'view_op', 'dangerous'
            description: Human-readable description for transaction name

        Returns:
            Dict with status, output, and optional changes/error info
        """
        if intent_type not in self.VALID_INTENTS:
            return {
                "status": "error",
                "output": "Invalid intent_type: '{}'. Must be one of: {}".format(
                    intent_type, ", ".join(sorted(self.VALID_INTENTS))
                ),
            }

        if intent_type == "dangerous":
            return self._handle_dangerous(code, doc, namespace, description, confirm=confirm)
        elif intent_type == "write":
            return self._handle_write(code, doc, namespace, description)
        else:
            # read and view_op — no transaction
            return self._handle_read(code, namespace)

    def _handle_read(self, code: str, namespace: Dict[str, Any]) -> Dict[str, Any]:
        """Execute code without a transaction (read / view_op)."""
        try:
            exec(code, namespace)
            output = self._collect_output(namespace)
            return {
                "status": "success",
                "output": output,
                "result": namespace.get("__result__"),
            }
        except Exception as e:
            return {
                "status": "error",
                "output": self._format_error(e),
                "error_type": type(e).__name__,
                "error_message": str(e),
            }

    def _handle_write(
        self, code: str, doc: Any, namespace: Dict[str, Any], description: str
    ) -> Dict[str, Any]:
        """Execute code wrapped in a Transaction."""
        DB = namespace.get("DB")
        if DB is None:
            return {
                "status": "error",
                "output": "DB (Autodesk.Revit.DB) not found in namespace",
            }

        t = None
        try:
            t = DB.Transaction(doc, "KUKAI AI: {}".format(description))
            t.Start()

            exec(code, namespace)

            t.Commit()
            output = self._collect_output(namespace)
            return {
                "status": "success",
                "output": output,
                "result": namespace.get("__result__"),
                "transaction": "committed",
            }
        except Exception as e:
            if t is not None:
                try:
                    if t.HasStarted() and not t.HasEnded():
                        t.RollBack()
                except Exception:
                    pass  # RollBack itself failed — nothing we can do
            return {
                "status": "error",
                "output": self._format_error(e),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "transaction": "rolled_back",
            }

    def _handle_dangerous(
        self, code: str, doc: Any, namespace: Dict[str, Any], description: str,
        confirm: bool = False,
    ) -> Dict[str, Any]:
        """
        Dangerous operations: return confirmation request WITHOUT executing.

        If confirm=True, execute immediately using TransactionGroup (same as write).
        """
        if confirm:
            # User explicitly confirmed — execute with transaction
            return self._handle_write(code, doc, namespace, description)

        # Extract a preview of what the code does (first 500 chars)
        preview_lines = code.strip().split("\n")[:20]
        preview = "\n".join(preview_lines)
        if len(code) > len("\n".join(preview_lines)):
            preview += "\n... ({} more chars)".format(
                len(code) - len("\n".join(preview_lines))
            )

        return {
            "status": "needs_confirmation",
            "output": "This operation is classified as DANGEROUS and requires confirmation.",
            "preview": preview,
            "description": description,
            "needs_confirmation": True,
        }

    def _collect_output(self, namespace: Dict[str, Any]) -> str:
        """Collect captured print output from namespace."""
        captured = namespace.get("__captured_output__", [])
        if not captured:
            # Try the captured_output list passed into safe_namespace
            # It's stored in the print closure, but also check builtins
            pass
        return "".join(captured) if captured else ""

    def _format_error(self, e: Exception) -> str:
        """Format exception with full traceback."""
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        return "".join(tb)
