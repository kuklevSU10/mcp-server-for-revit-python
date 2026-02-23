# -*- coding: utf-8 -*-
"""BIM VOR Generate — auto-generate VOR positions from BIM semantic groups."""
import json
import os
from mcp.server.fastmcp import Context
from ._constants import FT3_TO_M3, FT2_TO_M2

# Re-use helpers from vor_vs_bim (same patterns path)
from .vor_vs_bim import (
    _load_patterns,
    _fetch_bim_summary,
    PATTERNS_PATH,
)

# Group filter mappings: top-level group keys per filter
GROUP_FILTER_MAP = {
    "structural":    ["structural"],
    "architectural": ["architectural", "generic"],
    "mep":           ["mep"],
    "all":           [],  # empty = no filter
}

# Human-readable Russian unit labels per canonical unit
UNIT_LABEL = {
    "m3":    "м3",
    "m2":    "м2",
    "m":     "пог.м",
    "count": "шт",
    "piece": "шт",
}


def register_bim_vor_generate_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register bim_vor_generate tool."""

    @mcp_server.tool()
    async def bim_vor_generate(
        group_filter: str = "all",
        min_volume: float = 0.0,
        ctx: Context = None,
    ) -> dict:
        """Auto-generate VOR (work breakdown) positions from BIM model using semantic grouping.

        Returns ready-to-use VOR positions with volumes from the model.
        group_filter: filter by group ('all', 'structural', 'architectural', 'mep')
        min_volume: skip positions with volume below this threshold
        """
        # Validate group_filter
        if group_filter not in GROUP_FILTER_MAP:
            return {
                "error": "Invalid group_filter. Use: all, structural, architectural, mep",
                "valid": list(GROUP_FILTER_MAP.keys()),
            }

        # Load semantic patterns
        patterns = _load_patterns()
        if not patterns:
            return {"error": "Could not load global_patterns.json", "path": PATTERNS_PATH}

        # Build id -> pattern info map
        id_to_pattern = {p["id"]: p for p in patterns if "id" in p}

        # Fetch BIM summary from Revit
        summary = await _fetch_bim_summary(revit_post, ctx)
        if summary is None:
            return {"error": "Could not fetch BIM data from Revit"}

        # Determine allowed top-level group keys
        allowed_tops = GROUP_FILTER_MAP.get(group_filter, [])

        # Walk summary and build positions
        positions = []
        pos_id = 1
        model_stats = {"structural": 0, "architectural": 0, "mep": 0, "other": 0}

        for top_key, sub_dict in summary.items():
            if top_key.startswith("_"):
                continue
            if not isinstance(sub_dict, dict):
                continue
            # Apply group_filter
            if allowed_tops and top_key not in allowed_tops:
                continue

            for sub_key, grp in sub_dict.items():
                if not isinstance(grp, dict):
                    continue

                label = grp.get("label", sub_key)
                vol_m3 = grp.get("total_volume_m3", 0.0) or 0.0
                area_m2 = grp.get("total_area_m2", 0.0) or 0.0
                length_m = grp.get("total_length_m", 0.0) or 0.0
                count = grp.get("total_count", 0) or 0
                breakdown = grp.get("breakdown", [])

                # Determine pattern_id for this group (first matching)
                group_str = top_key + "." + sub_key
                pattern_id = None
                pat_unit = "count"
                for pid, pat in id_to_pattern.items():
                    if pat.get("group", "") == group_str:
                        pattern_id = pid
                        pat_unit = pat.get("unit", "count")
                        break

                # Pick canonical volume value
                if pat_unit == "m3":
                    vol_value = vol_m3
                elif pat_unit == "m2":
                    vol_value = area_m2
                elif pat_unit == "m":
                    vol_value = length_m
                else:
                    vol_value = float(count)

                # Apply min_volume filter
                if vol_value < min_volume:
                    continue

                unit_label = UNIT_LABEL.get(pat_unit, pat_unit)
                bim_types = [b.get("type", "") for b in breakdown[:10] if b.get("type")]

                positions.append({
                    "id":         pos_id,
                    "name":       label,
                    "unit":       unit_label,
                    "volume":     round(vol_value, 3),
                    "volume_m3":  round(vol_m3,   3),
                    "area_m2":    round(area_m2,  3),
                    "length_m":   round(length_m, 3),
                    "count":      count,
                    "pattern_id": pattern_id,
                    "group":      group_str,
                    "top_group":  top_key,
                    "bim_types":  bim_types,
                })
                pos_id += 1

                # Accumulate stats
                stat_key = top_key if top_key in model_stats else "other"
                model_stats[stat_key] += vol_value

        # Sort positions: structural first, then by volume descending
        group_order = {"structural": 0, "architectural": 1, "mep": 2}
        positions.sort(
            key=lambda p: (group_order.get(p["top_group"], 3), -p["volume"])
        )
        # Re-number after sort
        for i, p in enumerate(positions, 1):
            p["id"] = i

        return {
            "positions":      positions,
            "total_positions": len(positions),
            "group_filter":   group_filter,
            "min_volume":     min_volume,
            "model_stats": {
                "structural_total_m3":    round(model_stats.get("structural", 0), 3),
                "architectural_total":    round(model_stats.get("architectural", 0), 3),
                "mep_total_m":            round(model_stats.get("mep", 0), 3),
                "patterns_loaded":        len(patterns),
            },
        }
