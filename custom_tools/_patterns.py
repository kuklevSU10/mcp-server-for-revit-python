# -*- coding: utf-8 -*-
"""
_patterns.py — shared pattern loading and matching for BIM Semantic Layer.

Single source for _load_patterns() and PATTERNS_PATH.
Eliminates duplication between bim_summary.py and vor_vs_bim.py.
"""
import json
import os

# Path to global_patterns.json in bim-semantic-layer
PATTERNS_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', '..', 'bim-semantic-layer', 'global_patterns.json'
)


def load_patterns():
    """Load patterns list from global_patterns.json.

    Returns list of pattern dicts, or empty list on failure.
    Each pattern has: id, label, group, keywords, categories,
    optional: regex, negative_keywords, priority, canonical_unit.
    """
    try:
        path = os.path.normpath(PATTERNS_PATH)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get('patterns', [])
        return data
    except Exception:
        return []
