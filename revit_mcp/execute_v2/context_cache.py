"""
Context Cache — speeds up Revit context collection.

Caches levels (rarely changes) and categories summary (ttl-based).
"""

import threading
import time
from typing import Any, Dict

class ContextCache:
    """Thread-safe cache for context components."""
    
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._cache = {}
        self._cache_lock = threading.Lock()
        self._ttl = {
            "levels": 300,            # 5 minutes
            "categories_summary": 120, # 2 minutes
        }

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get(self, key: str) -> Any:
        with self._cache_lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() - entry["ts"] <= self._ttl.get(key, 0):
                    return entry["data"]
            return None

    def set(self, key: str, data: Any):
        with self._cache_lock:
            self._cache[key] = {
                "ts": time.time(),
                "data": data
            }

    def clear(self):
        with self._cache_lock:
            self._cache.clear()
