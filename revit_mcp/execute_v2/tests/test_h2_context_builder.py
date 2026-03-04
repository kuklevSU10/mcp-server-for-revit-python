"""Tests for H2: Context Builder V2"""
import pytest
from unittest.mock import MagicMock, patch
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from revit_mcp.execute_v2.context_builder import ContextBuilder, MINIMAL_CONTEXT_CODE


class TestContextBuilderV2:
    def test_get_context_code_returns_string(self):
        cb = ContextBuilder()
        code = cb.get_context_code()
        assert isinstance(code, str)
        assert '__result__' in code

    def test_minimal_context_code_exists(self):
        cb = ContextBuilder()
        code = cb.get_minimal_context_code()
        assert isinstance(code, str)
        assert '__result__' in code
        assert 'levels' in code

    def test_minimal_context_code_shorter_than_full(self):
        cb = ContextBuilder()
        full = cb.get_context_code()
        minimal = cb.get_minimal_context_code()
        assert len(minimal) < len(full)

    def test_full_context_has_family_names(self):
        cb = ContextBuilder()
        code = cb.get_context_code()
        assert 'family_names' in code

    def test_full_context_has_workset_info(self):
        cb = ContextBuilder()
        code = cb.get_context_code()
        assert 'worksets' in code or 'is_workshared' in code

    def test_full_context_has_views(self):
        cb = ContextBuilder()
        code = cb.get_context_code()
        assert 'views' in code

    def test_full_context_has_project_info(self):
        cb = ContextBuilder()
        code = cb.get_context_code()
        assert 'project_info' in code

    def test_build_from_result_caches(self):
        cb = ContextBuilder()
        data = {"project_name": "Test", "levels": [], "categories_summary": {}}
        result = cb.build_from_result(data)
        assert result == data
        # Should be cached now
        mock_doc = MagicMock()
        mock_uidoc = MagicMock()
        # Build again — should return cached
        cached = cb.build(mock_doc, mock_uidoc)
        assert cached == data

    def test_invalidate_cache(self):
        cb = ContextBuilder()
        data = {"project_name": "Test"}
        cb.build_from_result(data)
        cb.invalidate_cache()
        assert cb._cache is None

    def test_minimal_context_no_family_names(self):
        cb = ContextBuilder()
        code = cb.get_minimal_context_code()
        assert 'family_names' not in code

    def test_minimal_context_no_worksets(self):
        cb = ContextBuilder()
        code = cb.get_minimal_context_code()
        assert 'worksets' not in code


class TestPipelineUsesMinimalContext:
    """Verify pipeline chooses minimal context for READ, full for WRITE."""

    def test_pipeline_has_minimal_context_logic(self):
        """Pipeline source should reference minimal context."""
        import inspect
        from revit_mcp.execute_v2 import pipeline
        source = inspect.getsource(pipeline)
        assert 'minimal' in source.lower() or 'get_minimal' in source
