"""
Code Cache — caches generated IronPython code for identical requests.
"""

import hashlib
import json
import threading
import time
from typing import Optional

class CodeCache:
    """Thread-safe cache for generated code."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._ttl = 600  # 10 minutes
        self._max_size = 50

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _make_key(self, user_request: str, context: dict) -> str:
        """Create cache key from request and context."""
        ctx_str = json.dumps(context, sort_keys=True, default=str)
        return hashlib.sha256((user_request + ctx_str).encode('utf-8')).hexdigest()

    def get(self, user_request: str, context: dict) -> Optional[dict]:
        key = self._make_key(user_request, context)
        with self._cache_lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry["ts"] <= self._ttl:
                    # Move to end (LRU)
                    del self._cache[key]
                    self._cache[key] = entry
                    return entry["result"]
            return None

    def set(self, user_request: str, context: dict, result: dict):
        key = self._make_key(user_request, context)
        with self._cache_lock:
            if len(self._cache) >= self._max_size:
                # Evict oldest (first item in dict)
                oldest = next(iter(self._cache))
                del self._cache[oldest]
            self._cache[key] = {
                "ts": time.time(),
                "result": result
            }

    def clear(self):
        with self._cache_lock:
            self._cache.clear()
