"""
Session State — thread-safe memory between requests in a dialogue.

Stores element IDs, arbitrary context, and generates prompt snippets
for LLM context injection.
"""

import threading
import time
from typing import Any, Dict, List, Optional


class SessionState:
    """Thread-safe storage for state between requests."""

    def __init__(self, session_id: str, ttl_seconds: int = 3600):
        """
        Args:
            session_id: Unique session identifier.
            ttl_seconds: Session expires after this many seconds of inactivity.
        """
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._elements: Dict[str, List[int]] = {}
        self._context: Dict[str, Any] = {}
        self._last_request: Optional[str] = None
        self._history: List[Dict[str, str]] = []

    def _touch(self):
        """Update last activity timestamp."""
        self._last_activity = time.time()

    def add_to_history(self, role: str, content: str, code: str = None):
        """Add a message to the conversation history."""
        with self._lock:
            self._touch()
            entry = {"role": role, "content": content}
            if code:
                entry["code"] = code
            self._history.append(entry)

    def get_history_snippet(self, max_turns: int = 3) -> str:
        """Get recent conversation history for LLM context."""
        with self._lock:
            if not self._history:
                return ""
            
            # Get last N messages (usually want pairs, so 2*max_turns)
            recent = self._history[-(max_turns * 2):]
            parts = ["=== ИСТОРИЯ ДИАЛОГА ==="]
            for msg in recent:
                parts.append("{}: {}".format(msg["role"].capitalize(), msg["content"]))
            return "\n".join(parts)

    def store_elements(self, elements: list, label: str = "last_result"):
        """
        Store a list of ElementId (as ints) with a label.

        Args:
            elements: List of element IDs (ints).
            label: Label for this set of elements.
        """
        with self._lock:
            self._touch()
            self._elements[label] = [int(e) for e in elements]

    def get_elements(self, label: str = "last_result") -> list:
        """
        Retrieve stored ElementIds by label.

        Args:
            label: Label to look up.

        Returns:
            List of element IDs (ints), or empty list if not found.
        """
        with self._lock:
            self._touch()
            return list(self._elements.get(label, []))

    def store_context(self, key: str, value: Any):
        """Store arbitrary context value."""
        with self._lock:
            self._touch()
            self._context[key] = value

    def get_context(self, key: str, default=None) -> Any:
        """Retrieve context value by key."""
        with self._lock:
            self._touch()
            return self._context.get(key, default)

    def set_last_request(self, request: str):
        """Store the last user request text."""
        with self._lock:
            self._touch()
            self._last_request = request

    def clear(self):
        """Clear all stored state."""
        with self._lock:
            self._elements.clear()
            self._context.clear()
            self._last_request = None
            self._history.clear()
            self._touch()

    def is_expired(self) -> bool:
        """Check if session has expired due to inactivity."""
        with self._lock:
            return (time.time() - self._last_activity) > self.ttl_seconds

    def to_prompt_snippet(self) -> str:
        """
        Generate a string for LLM prompt injection describing session state.

        Returns:
            Human-readable summary, or empty string if no state.
        """
        with self._lock:
            parts = []

            # Add history if available
            if self._history:
                recent = self._history[-6:]  # Last 3 turns (user+assistant)
                parts.append("=== ИСТОРИЯ ДИАЛОГА ===")
                for msg in recent:
                    parts.append("{}: {}".format(msg["role"].capitalize(), msg["content"]))
                parts.append("=======================")

            if self._last_request:
                parts.append("Предыдущий запрос: {}".format(self._last_request))

            for label, ids in self._elements.items():
                count = len(ids)
                if count <= 10:
                    ids_str = str(ids)
                else:
                    ids_str = "{}... (всего {})".format(str(ids[:10]), count)
                parts.append("Сохранённые элементы '{}': {} шт. (IDs: {})".format(label, count, ids_str))

            for key, value in self._context.items():
                parts.append("{}: {}".format(key, value))

            return "\n".join(parts)


class SessionManager:
    """Global session manager (singleton)."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
        self._sessions_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "SessionManager":
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

    def get_or_create(self, session_id: str) -> SessionState:
        """
        Get existing session or create a new one.

        Args:
            session_id: Unique session identifier.

        Returns:
            SessionState instance.
        """
        with self._sessions_lock:
            if session_id in self._sessions:
                session = self._sessions[session_id]
                if not session.is_expired():
                    return session
                # Expired — create new
                del self._sessions[session_id]

            session = SessionState(session_id)
            self._sessions[session_id] = session
            return session

    def cleanup_expired(self):
        """Remove all expired sessions."""
        with self._sessions_lock:
            expired = [
                sid for sid, s in self._sessions.items() if s.is_expired()
            ]
            for sid in expired:
                del self._sessions[sid]
            return len(expired)
