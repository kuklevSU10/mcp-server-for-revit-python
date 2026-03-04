"""
Audit Log — JSONL logging of all execute_v2 operations.

One file per day: audit_YYYY-MM-DD.jsonl
Logs code hash (not full code) for privacy.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional


# Default log directory
DEFAULT_LOG_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "logs", "execute_v2"
)


class AuditLog:
    """Logs all execute_v2 operations to JSONL files."""

    def __init__(self, log_dir: str = None):
        """
        Args:
            log_dir: Directory for log files.
                     Default: E:\\RevitExpert\\logs\\execute_v2\\
        """
        self.log_dir = log_dir or os.path.normpath(DEFAULT_LOG_DIR)
        os.makedirs(self.log_dir, exist_ok=True)

    def _log_path(self, date: datetime = None) -> str:
        """Get log file path for a given date."""
        if date is None:
            date = datetime.now()
        filename = "audit_{}.jsonl".format(date.strftime("%Y-%m-%d"))
        return os.path.join(self.log_dir, filename)

    @staticmethod
    def _code_hash(code: str) -> str:
        """SHA256 hash of code, first 8 chars."""
        if not code:
            return ""
        return hashlib.sha256(code.encode("utf-8")).hexdigest()[:8]

    def log_execution(
        self,
        session_id: str,
        user_request: str,
        intent_type: str,
        code_executed: str,
        result_status: str,
        retries: int,
        duration_ms: float,
        model_used: str = None,
        error: str = None,
        traceback: str = None,
    ):
        """
        Write a single execution record to the daily log file.

        Args:
            session_id: Session identifier.
            user_request: Original user request text.
            intent_type: Classified intent (read/write/dangerous/view_op).
            code_executed: The executed code (only hash is stored).
            result_status: Result status (success/error/rejected).
            retries: Number of retry attempts.
            duration_ms: Execution duration in milliseconds.
            model_used: LLM model used.
            error: Error message if any.
            traceback: Full traceback if any.
        """
        record = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "request": user_request[:200],
            "intent": intent_type,
            "status": result_status,
            "retries": retries,
            "duration_ms": round(duration_ms, 1),
            "model": model_used,
            "code_hash": self._code_hash(code_executed),
        }
        if error:
            record["error"] = error
        if traceback:
            record["traceback"] = traceback

        log_path = self._log_path()
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # Fail silently — logging should never break execution
            pass

    def get_stats(self, days: int = 7) -> Dict:
        """
        Aggregate statistics for the last N days.

        Args:
            days: Number of days to look back.

        Returns:
            {
                "total": int,
                "success": int,
                "error": int,
                "rejected": int,
                "avg_retries": float,
                "avg_duration_ms": float,
                "by_intent": {"read": N, "write": N, ...},
                "by_model": {"model/name": N, ...},
            }
        """
        total = 0
        success = 0
        error = 0
        rejected = 0
        total_retries = 0
        total_duration = 0.0
        by_intent: Dict[str, int] = {}
        by_model: Dict[str, int] = {}

        now = datetime.now()
        for i in range(days):
            date = now - timedelta(days=i)
            log_path = self._log_path(date)
            if not os.path.exists(log_path):
                continue
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        total += 1
                        status = rec.get("status", "")
                        if status == "success":
                            success += 1
                        elif status == "error":
                            error += 1
                        elif status == "rejected":
                            rejected += 1

                        total_retries += rec.get("retries", 0)
                        total_duration += rec.get("duration_ms", 0)

                        intent = rec.get("intent", "unknown")
                        by_intent[intent] = by_intent.get(intent, 0) + 1

                        model = rec.get("model") or "unknown"
                        by_model[model] = by_model.get(model, 0) + 1

            except OSError:
                continue

        return {
            "total": total,
            "success": success,
            "error": error,
            "rejected": rejected,
            "avg_retries": round(total_retries / total, 2) if total else 0.0,
            "avg_duration_ms": round(total_duration / total, 1) if total else 0.0,
            "by_intent": by_intent,
            "by_model": by_model,
        }
