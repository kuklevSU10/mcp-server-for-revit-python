# -*- coding: utf-8 -*-
"""
MCP tool: nw_get_volumes
Navisworks Quantification / volume extraction.
Used for cross-checking with Revit bim_volumes.
"""

import asyncio
from typing import Optional
from ._navisworks_client import _nw_call


async def nw_get_volumes(category: Optional[str] = None) -> dict:
    """
    Объёмы элементов из Navisworks Quantification (кросс-проверка с bim_volumes).

    Если Quantification (Takeoff) не настроен, возвращает приближение
    на основе BoundingBox элементов.

    Args:
        category: Фильтр по категории, например "Walls", "Floors", "Стены".
                  Если None — все категории.

    Returns:
        {
            "method": "takeoff" | "bbox_approximation",
            "category_filter": "Walls",
            "total_volume_m3": 1234.567,
            "categories": [
                {"category": "Walls", "volume_m3": 847.3},
                {"category": "Floors", "volume_m3": 387.267}
            ],
            "note": "..."
        }

    Cross-check tip:
        Compare with bim_volumes() from Revit:
        delta < 5% = OK, delta > 10% = investigate geometry discrepancy
    """
    route = "/quantify/volumes"
    if category:
        try:
            from urllib.parse import urlencode
        except ImportError:
            from urllib import urlencode
        route += "?" + urlencode({"category": category})

    result = await asyncio.to_thread(_nw_call, route, "GET", None, 60)
    return result


def register_navisworks_volumes_tools(mcp_server, *args, **kwargs):
    """Register volume tools with the MCP server."""
    mcp_server.tool()(nw_get_volumes)
