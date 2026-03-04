"""
Result Formatter — template-based formatting of execution results.

Converts raw execution results into human-readable text.
NO LLM calls — pure template logic.
"""

from typing import Dict


class ResultFormatter:
    """
    Formats execution results into user-friendly messages.
    
    Uses emoji prefixes and structured output based on status and intent.
    """

    def format(self, execution_result: Dict, user_request: str, intent_type: str) -> str:
        """
        Format execution result into human-readable text.

        Args:
            execution_result: Dict from TransactionExecutor.execute()
                Expected keys: status, output, result, error_type, error_message
            user_request: Original user request (for context).
            intent_type: Intent classification.

        Returns:
            Formatted string with emoji prefix.
        """
        status = execution_result.get("status", "unknown")

        if status == "success":
            return self._format_success(execution_result, intent_type)
        elif status == "error":
            return self._format_error(execution_result)
        elif status == "needs_confirmation":
            return self._format_confirmation(execution_result)
        elif status == "rejected":
            return self._format_rejected(execution_result)
        else:
            return "Status: {}".format(status)

    def _format_success(self, result: Dict, intent_type: str) -> str:
        """Format successful execution."""
        r = result.get("result")  # __result__ dict from code

        if isinstance(r, dict):
            summary = r.get("summary", "")
            count = r.get("count")
            details = r.get("details", [])

            # Choose prefix based on intent
            if intent_type == "write":
                prefix = "done"
            elif intent_type == "view_op":
                prefix = "view"
            else:
                prefix = "info"

            parts = []
            if summary:
                parts.append(summary)
            elif count is not None:
                parts.append("Обработано элементов: {}".format(count))

            # Add detail preview (first 5 items)
            if details and len(details) > 0:
                detail_lines = []
                shown = min(len(details), 5)
                for item in details[:shown]:
                    if isinstance(item, dict):
                        # Format dict items as key=value pairs
                        pairs = []
                        for k, v in item.items():
                            pairs.append("{}: {}".format(k, v))
                        detail_lines.append(", ".join(pairs))
                    else:
                        detail_lines.append(str(item))
                if len(details) > shown:
                    detail_lines.append("... и ещё {}".format(len(details) - shown))
                parts.append("\n".join(detail_lines))

            text = "\n".join(parts) if parts else "Выполнено успешно"
            return self._add_prefix(prefix, text)
        else:
            # No structured result — use captured output
            output = result.get("output", "")
            if output:
                return self._add_prefix("info", output.strip())
            return self._add_prefix("done", "Выполнено успешно")

    def _format_error(self, result: Dict) -> str:
        """Format error result."""
        error_type = result.get("error_type", "Error")
        error_message = result.get("error_message", result.get("output", "Unknown error"))

        text = "{}: {}".format(error_type, error_message)
        return self._add_prefix("error", text)

    def _format_confirmation(self, result: Dict) -> str:
        """Format confirmation request for dangerous operations."""
        description = result.get("description", "операция")
        preview = result.get("preview", "")

        parts = ["Требует подтверждения: {}".format(description)]
        if preview:
            parts.append("Код:\n{}".format(preview[:500]))
        return self._add_prefix("warning", "\n".join(parts))

    def _format_rejected(self, result: Dict) -> str:
        """Format rejected code (sandbox validation failed)."""
        reason = result.get("reason", "Unknown")
        return self._add_prefix("blocked", "Код отклонён: {}".format(reason))

    @staticmethod
    def _add_prefix(kind: str, text: str) -> str:
        """Add emoji prefix based on message kind."""
        prefixes = {
            "done": "✅",
            "info": "📋",
            "view": "👁",
            "error": "❌",
            "warning": "⚠️",
            "blocked": "🚫",
        }
        prefix = prefixes.get(kind, "")
        if prefix:
            return "{} {}".format(prefix, text)
        return text
