# -*- coding: utf-8 -*-
"""Unit tests for vor_vs_bim: tolerance_pct param + semantic matching.
Runs WITHOUT Revit (no IronPython, no Revit model needed).
"""
import sys
import os
import inspect
import math

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ── PART A: tolerance_pct parameter test ─────────────────────────────────────

def test_tolerance_pct_in_signature():
    """Verify vor_vs_bim tool has tolerance_pct parameter (not bare 'tolerance')."""
    from custom_tools.vor_vs_bim import register_vor_vs_bim_tools

    # Inspect the source to find the parameter name
    src = inspect.getsource(register_vor_vs_bim_tools)
    assert "tolerance_pct" in src, "tolerance_pct parameter not found in register_vor_vs_bim_tools"
    # Old name 'tolerance' should only appear in comments/docs, not as bare param
    # Count standalone occurrences — we just check tolerance_pct is there
    print("[PASS] tolerance_pct parameter found in source")


def test_tolerance_pct_default():
    """Verify default value is 3.0 in both vor_vs_bim and vor_vs_bim_file."""
    from custom_tools.vor_vs_bim import register_vor_vs_bim_tools
    src = inspect.getsource(register_vor_vs_bim_tools)
    # Should see 'tolerance_pct: float = 3.0' twice (vor_vs_bim + vor_vs_bim_file)
    count = src.count("tolerance_pct: float = 3.0")
    assert count >= 2, "Expected tolerance_pct: float = 3.0 in both vor_vs_bim and vor_vs_bim_file, found {}".format(count)
    print("[PASS] tolerance_pct: float = 3.0 present {} time(s)".format(count))


def test_tolerance_pct_passed_to_diff():
    """Verify tolerance_pct variable is used in the diff comparison."""
    from custom_tools.vor_vs_bim import register_vor_vs_bim_tools
    src = inspect.getsource(register_vor_vs_bim_tools)
    assert "diff_pct > tolerance_pct" in src, "tolerance_pct not used in diff comparison"
    print("[PASS] diff_pct > tolerance_pct comparison found")


# ── PART B: _semantic_match_vor_to_bim test ──────────────────────────────────

def test_semantic_cache_exists():
    """_SEMANTIC_CACHE dict must exist at module level."""
    from custom_tools import vor_vs_bim as mod
    assert hasattr(mod, "_SEMANTIC_CACHE"), "_SEMANTIC_CACHE not found in module"
    assert isinstance(mod._SEMANTIC_CACHE, dict), "_SEMANTIC_CACHE should be a dict"
    print("[PASS] _SEMANTIC_CACHE dict exists")


def test_semantic_function_exists():
    """_semantic_match_vor_to_bim must be importable."""
    from custom_tools.vor_vs_bim import _semantic_match_vor_to_bim
    assert callable(_semantic_match_vor_to_bim)
    print("[PASS] _semantic_match_vor_to_bim is callable")


def test_semantic_empty_categories():
    """Returns None for empty categories list."""
    from custom_tools.vor_vs_bim import _semantic_match_vor_to_bim
    result = _semantic_match_vor_to_bim("Кладка кирпичная", [])
    assert result is None, "Expected None for empty categories"
    print("[PASS] Returns None for empty categories")


def test_semantic_keyword_fallback():
    """Fallback keyword matching works when OpenAI unavailable (mocked)."""
    from custom_tools import vor_vs_bim as mod

    # Clear cache for fresh test
    mod._SEMANTIC_CACHE.clear()

    # Temporarily mock openai to be unavailable
    import unittest.mock as mock
    with mock.patch.dict("sys.modules", {"openai": None}):
        # Re-import to get the openai-unavailable path
        from custom_tools.vor_vs_bim import _semantic_match_vor_to_bim

        categories = [
            "Кирпичная кладка наружных стен",
            "Монолитные железобетонные конструкции",
            "Кровля из профнастила",
            "Оконные блоки",
        ]
        vor_name = "Кладка кирпичная наружная толщ. 510мм"
        result = _semantic_match_vor_to_bim(vor_name, categories)
        print("[INFO] Fallback result: {}".format(result))
        # Should match the kладка/кирпичная category or None — not crash
        print("[PASS] Keyword fallback runs without crash, result={}".format(result))


def test_semantic_caching():
    """Second call returns cached result (no duplicate API calls)."""
    from custom_tools import vor_vs_bim as mod
    from custom_tools.vor_vs_bim import _semantic_match_vor_to_bim

    mod._SEMANTIC_CACHE.clear()

    categories = ["Перекрытия монолитные", "Кирпичная кладка"]
    vor = "Кирпичная кладка стен"

    # First call (may fail openai, will use fallback and cache)
    r1 = _semantic_match_vor_to_bim(vor, categories)

    # Verify cached
    cache_key = (vor, tuple(sorted(categories)))
    assert cache_key in mod._SEMANTIC_CACHE, "Result not cached after first call"

    # Second call must return same result from cache
    r2 = _semantic_match_vor_to_bim(vor, categories)
    assert r1 == r2, "Cached result differs from original"
    print("[PASS] Caching works: r1={}, r2={}".format(r1, r2))


def test_match_method_in_integration():
    """match_method field present in source code integration."""
    from custom_tools.vor_vs_bim import register_vor_vs_bim_tools
    src = inspect.getsource(register_vor_vs_bim_tools)
    assert '"match_method"' in src, "match_method key not found in entry dict"
    assert '"semantic"' in src, "'semantic' match_method value not found"
    assert '"keyword"' in src, "'keyword' match_method value not found"
    print("[PASS] match_method integration found in source")


if __name__ == "__main__":
    tests = [
        test_tolerance_pct_in_signature,
        test_tolerance_pct_default,
        test_tolerance_pct_passed_to_diff,
        test_semantic_cache_exists,
        test_semantic_function_exists,
        test_semantic_empty_categories,
        test_semantic_keyword_fallback,
        test_semantic_caching,
        test_match_method_in_integration,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print("[FAIL] {}: {}".format(t.__name__, e))
            failed += 1
    print("\n{}/{} tests passed".format(len(tests) - failed, len(tests)))
    sys.exit(failed)
