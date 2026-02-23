# -*- coding: utf-8 -*-
"""
MCP tool: get_navisworks_status
Returns status of the running Navisworks instance.
"""

from ._navisworks_client import _nw_call


async def get_navisworks_status() -> dict:
    """
    Статус запущенного Navisworks: версия, открытый файл, кол-во элементов.

    Returns:
        {
            "version": "2020",
            "status": "ok" | "no_document",
            "file": "path/to/model.nwd",
            "elements": 26548,
            "uptime_seconds": 3600,
            "port": 48885,
            "timestamp": "2026-02-23T12:00:00Z"
        }
        or {"error": "Navisworks не запущен..."}
    """
    import asyncio
    return await asyncio.to_thread(_nw_call, "/status", "GET", None, 10)


def register_navisworks_status_tools(mcp_server, *args, **kwargs):
    """Register get_navisworks_status with the MCP server."""
    mcp_server.tool()(get_navisworks_status)
