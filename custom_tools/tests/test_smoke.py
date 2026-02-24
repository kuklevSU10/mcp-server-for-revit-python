# -*- coding: utf-8 -*-
"""
test_smoke.py — smoke tests for _constants.py and _patterns.py.

Import strategy: use importlib.util.spec_from_file_location to load
_constants and _patterns DIRECTLY (bypassing custom_tools/__init__.py
which pulls in MCP/Revit dependencies unavailable in plain CPython).
"""
import os
import unittest
import importlib.util

# ---------------------------------------------------------------------------
# Direct module imports (no Revit DLLs required)
# ---------------------------------------------------------------------------
_TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _load(name, filename):
    path = os.path.join(_TOOLS_DIR, filename)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_constants = _load('_constants', '_constants.py')
_patterns  = _load('_patterns',  '_patterns.py')

CAT_OST_MAP       = _constants.CAT_OST_MAP
CATEGORY_REGISTRY = _constants.CATEGORY_REGISTRY
ironpython_cat_map = _constants.ironpython_cat_map
load_patterns      = _patterns.load_patterns


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestCatOstMap(unittest.TestCase):

    def test_cat_ost_map_not_empty(self):
        """CAT_OST_MAP должен содержать > 10 категорий."""
        self.assertGreater(len(CAT_OST_MAP), 10,
            'CAT_OST_MAP too small: {}'.format(len(CAT_OST_MAP)))

    def test_category_registry_complete(self):
        """CATEGORY_REGISTRY должен содержать > 20 записей."""
        self.assertGreater(len(CATEGORY_REGISTRY), 20,
            'CATEGORY_REGISTRY too small: {}'.format(len(CATEGORY_REGISTRY)))

    def test_ironpython_cat_map_returns_string(self):
        """ironpython_cat_map(['Walls']) должен вернуть строку с 'OST_Walls'."""
        result = ironpython_cat_map(['Walls'])
        self.assertIsInstance(result, str)
        self.assertIn('OST_Walls', result)

    def test_ironpython_cat_map_unknown_category_skipped(self):
        """Неизвестная категория не должна вызывать исключение."""
        result = ironpython_cat_map(['NonExistentCategory'])
        self.assertIsInstance(result, str)


class TestPatterns(unittest.TestCase):

    def test_load_patterns_returns_list(self):
        """load_patterns() должен вернуть list длиной > 50."""
        result = load_patterns()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 50,
            'load_patterns returned only {} patterns'.format(len(result)))

    def test_pattern_has_required_fields(self):
        """Каждый pattern должен содержать поля 'keywords' и 'group'."""
        patterns = load_patterns()
        self.assertTrue(len(patterns) > 0, 'No patterns loaded')
        for pat in patterns:
            pid = pat.get('id', '<no id>')
            self.assertIn('keywords', pat,
                "Pattern '{}' missing 'keywords' field".format(pid))
            self.assertIn('group', pat,
                "Pattern '{}' missing 'group' field".format(pid))


if __name__ == '__main__':
    unittest.main(verbosity=2)
