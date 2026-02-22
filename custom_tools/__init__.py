# -*- coding: utf-8 -*-
"""Custom tender tools for Revit MCP Server (SU-10 Analytics)
These tools are separate from upstream to avoid merge conflicts.
"""
from .bim_volumes import register_bim_volumes_tools
from .bim_to_vor import register_bim_to_vor_tools
from .vor_vs_bim import register_vor_vs_bim_tools
from .bim_audit import register_bim_audit_tools
from .bim_report import register_bim_report_tools


def register_custom_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func):
    """Register all custom tender tools with the MCP server."""
    register_bim_volumes_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_to_vor_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_vor_vs_bim_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_audit_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
    register_bim_report_tools(mcp_server, revit_get_func, revit_post_func, revit_image_func)
