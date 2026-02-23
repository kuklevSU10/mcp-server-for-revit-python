# -*- coding: utf-8 -*-
"""
MCP tools: nw_get_clashes, nw_run_clash
Navisworks Clash Detective integration.
"""

import asyncio
from typing import Optional
from ._navisworks_client import _nw_call


async def nw_get_clashes(test_name: Optional[str] = None) -> dict:
    """
    Список clash tests и их результатов из Navisworks Clash Detective.

    Args:
        test_name: Если указан — возвращает только этот тест.
                   Если None — возвращает все тесты.

    Returns:
        {
            "tests": [
                {
                    "name": "КР vs ОВиК",
                    "status": "Done",
                    "total_clashes": 47,
                    "by_status": {"New": 32, "Active": 12, "Resolved": 3},
                    "last_run": "2026-02-23T12:00:00Z"
                }
            ],
            "count": 3
        }
    """
    result = await asyncio.to_thread(_nw_call, "/clash/list", "GET", None, 30)

    if "error" in result:
        return result

    if test_name:
        # Filter to requested test
        tests = result.get("tests", [])
        matched = [t for t in tests if test_name.lower() in t.get("name", "").lower()]
        if not matched:
            return {
                "error": "Clash test not found: {}".format(test_name),
                "available_tests": [t.get("name") for t in tests]
            }
        return {"tests": matched, "count": len(matched)}

    return result


async def nw_run_clash(test_name: str) -> dict:
    """
    Запустить clash test в Navisworks и получить список коллизий.

    Args:
        test_name: Точное или частичное имя теста (регистронезависимо).
                   Например: "КР vs ОВиК", "Structural vs MEP"

    Returns:
        {
            "test_name": "КР vs ОВиК",
            "total_clashes": 47,
            "clashes": [
                {
                    "id": "Clash1",
                    "status": "New",
                    "distance": -0.15,
                    "level": "01 Этаж",
                    "description": "New — Clash1"
                },
                ...
            ],
            "run_at": "2026-02-23T12:00:00Z"
        }
    """
    if not test_name:
        return {"error": "test_name is required"}

    # URL-encode the test name for the route
    try:
        from urllib.parse import quote
        encoded = quote(test_name, safe="")
    except ImportError:
        import urllib
        encoded = urllib.quote(test_name.encode("utf-8"), safe="")

    route = "/clash/run/{}".format(encoded)
    result = await asyncio.to_thread(_nw_call, route, "POST", {}, 120)

    if "error" in result:
        return result

    # Enrich summary
    clashes = result.get("clashes", [])
    by_status = {}
    for c in clashes:
        s = c.get("status", "Unknown")
        by_status[s] = by_status.get(s, 0) + 1

    result["by_status"] = by_status
    return result


def register_navisworks_clash_tools(mcp_server, *args, **kwargs):
    """Register clash tools with the MCP server."""
    mcp_server.tool()(nw_get_clashes)
    mcp_server.tool()(nw_run_clash)
