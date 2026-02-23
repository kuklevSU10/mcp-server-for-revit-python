# -*- coding: utf-8 -*-
"""Custom BIM tender tools for Revit MCP Server.
These tools are separate from upstream to avoid merge conflicts.
"""
from .bim_volumes import register_bim_volumes_tools
from .bim_audit import register_bim_audit_tools
from .bim_report import register_bim_report_tools
# BIM Semantic Layer
from .bim_catalog import register_bim_catalog_tools
from .bim_inspect import register_bim_inspect_tools
from .bim_search import register_bim_search_tools
from .bim_summary import register_bim_summary_tools
from .bim_links import register_bim_links_tools
from .bim_export import register_bim_export_tools
# New semantic tender tools (v2 — semantic matching)
from .vor_vs_bim import register_vor_vs_bim_tools
from .bim_vor_generate import register_bim_vor_generate_tools
from .bim_query import register_bim_query_tools


def register_custom_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func):
    """Register all custom tender tools with the MCP server."""
    register_bim_volumes_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_audit_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_report_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    # BIM Semantic Layer
    register_bim_catalog_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_inspect_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_search_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_summary_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    # Linked Files support
    register_bim_links_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    # Excel Export
    register_bim_export_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    # New semantic tender tools (v2)
    register_vor_vs_bim_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_vor_generate_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_query_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
