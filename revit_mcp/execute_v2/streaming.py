"""
Progress Tracking — polling-based progress for long-running operations.

Revit Routes doesn't support SSE, so we use a registry + polling pattern.
Client polls GET /execute_v2/progress/{session_id}/ to get current status.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("kukai.execute_v2.streaming")


class ProgressTracker:
    """Thread-safe progress tracker for a single execution."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = threading.Lock()
        self._step = "pending"
        self._percent = 0
        self._message = ""
        self._result: Optional[Dict] = None
        self._is_done = False
        self._created_at = time.time()

    def update(self, step: str, percent: int, message: str = ""):
        """
        Update current progress.

        Args:
            step: Current pipeline step name.
                  One of: classifying, building_context, generating,
                  validating, executing, formatting, done.
            percent: Progress percentage (0-100).
            message: Optional human-readable status message.
        """
        with self._lock:
            self._step = step
            self._percent = max(0, min(100, percent))
            self._message = message

    def get_status(self) -> Dict:
        """
        Get current progress status.

        Returns:
            {"step": str, "percent": int, "message": str, "done": bool, "result": dict|None}
        """
        with self._lock:
            return {
                "step": self._step,
                "percent": self._percent,
                "message": self._message,
                "done": self._is_done,
                "result": self._result,
            }

    def done(self, result: Dict):
        """Mark execution as complete and store final result."""
        with self._lock:
            self._step = "done"
            self._percent = 100
            self._is_done = True
            self._result = result


class ProgressRegistry:
    """
    Singleton registry of all active ProgressTrackers.

    Thread-safe. Auto-cleans stale trackers older than 1 hour.
    """

    _instance = None
    _lock = threading.Lock()
    STALE_TIMEOUT = 3600  # 1 hour

    def __init__(self):
        self._trackers: Dict[str, ProgressTracker] = {}
        self._trackers_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "ProgressRegistry":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def _reset(cls):
        """Reset singleton (for testing only)."""
        with cls._lock:
            cls._instance = None

    def create(self, session_id: str) -> ProgressTracker:
        """Create a new ProgressTracker for the given session."""
        tracker = ProgressTracker(session_id)
        with self._trackers_lock:
            self._trackers[session_id] = tracker
            self._cleanup_stale()
        return tracker

    def get(self, session_id: str) -> Optional[ProgressTracker]:
        """Get a ProgressTracker by session ID, or None if not found."""
        with self._trackers_lock:
            return self._trackers.get(session_id)

    def _cleanup_stale(self):
        """Remove trackers older than STALE_TIMEOUT (called internally)."""
        now = time.time()
        stale = [
            sid for sid, t in self._trackers.items()
            if (now - t._created_at) > self.STALE_TIMEOUT
        ]
        for sid in stale:
            del self._trackers[sid]
