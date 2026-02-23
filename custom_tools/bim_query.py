# -*- coding: utf-8 -*-
"""BIM Query — natural-language search for BIM elements via semantic patterns."""
import json
import re
from mcp.server.fastmcp import Context

# Re-use pattern helpers from vor_vs_bim
from .vor_vs_bim import (
    _load_patterns,
    _build_reverse_index,
    _match_vor_name_to_pattern,
    PATTERNS_PATH,
)
# Re-use search code builder from bim_search
from .bim_search import _build_search_code, CAT_MAP_SEARCH


# ---------------------------------------------------------------------------
# NL parsing helpers
# ---------------------------------------------------------------------------

def _extract_category_from_query(query_lower):
    """Extract Revit category from NL query (Russian + English)."""
    mappings = [
        (['стен', 'wall', 'кладк', 'газобетон', 'кирпич'],              'Walls'),
        (['перекрыти', 'плит', 'пол', 'floor', 'slab'],                 'Floors'),
        (['кровл', 'roof', 'крыш'],                                      'Roofs'),
        (['потолок', 'ceiling'],                                         'Ceilings'),
        (['колонн', 'column', 'стойк'],                                  'Columns'),
        (['балк', 'beam', 'прогон', 'ригел', 'framing'],                 'StructuralFraming'),
        (['фундамент', 'foundation', 'подошв'],                          'StructuralFoundation'),
        (['дверь', 'двери', 'door'],                                     'Doors'),
        (['окн', 'window'],                                              'Windows'),
        (['лестниц', 'марш', 'ступен', 'stair'],                        'Stairs'),
        (['пандус', 'ramp'],                                             'Ramps'),
        (['труб', 'pipe', 'гвс', 'хвс', 'канализ'],                     'Pipes'),
        (['воздуховод', 'duct', 'вентил'],                               'Ducts'),
        (['кабельн', 'кабель', 'лоток', 'cable'],                       'CableTray'),
        (['мебель', 'furniture'],                                        'Furniture'),
        (['оборудован', 'mechanic', 'механич'],                          'MechanicalEquipment'),
        (['светильник', 'lighting'],                                     'LightingFixtures'),
        (['электр', 'electrical'],                                       'ElectricalEquipment'),
    ]
    for keywords, category in mappings:
        for kw in keywords:
            if kw in query_lower:
                return category
    return 'Walls'   # default fallback


def _extract_level_from_query(query_lower):
    """Extract level/floor number from NL query."""
    patterns_re = [
        r'на\s+(\d+)\s*[-\u0435\u0433\u043e\u043c]+\s*этаж',   # на 3-м этаже
        r'(\d+)\s*[-\u0439]?\s*этаж',                            # 3-й этаж / 3 этаж
        r'уровень\s*[:\s]\s*(\d+)',                              # уровень: 3
        r'level\s*[:\s]\s*(\d+)',                                # level: 3
        r'(\d+)\s+floor',                                        # 3 floor
    ]
    for pat in patterns_re:
        m = re.search(pat, query_lower)
        if m:
            return m.group(1)
    return ''


def _extract_height_filter(query_lower):
    """Extract height comparison from query, e.g. 'выше 5 метров' -> (gt, 5.0)."""
    patterns_re = [
        (r'выше\s+(\d+(?:\.\d+)?)\s*м', 'gt'),
        (r'ниже\s+(\d+(?:\.\d+)?)\s*м', 'lt'),
        (r'больше\s+(\d+(?:\.\d+)?)\s*м', 'gt'),
        (r'меньше\s+(\d+(?:\.\d+)?)\s*м', 'lt'),
        (r'above\s+(\d+(?:\.\d+)?)\s*m', 'gt'),
        (r'below\s+(\d+(?:\.\d+)?)\s*m', 'lt'),
    ]
    for pat, op in patterns_re:
        m = re.search(pat, query_lower)
        if m:
            return op, float(m.group(1))
    return None, None


def _extract_diameter_filter(query_lower):
    """Extract pipe diameter from query, e.g. 'диаметром 50мм' -> 50."""
    m = re.search(r'диаметр\w*\s+(\d+)\s*мм', query_lower)
    if not m:
        m = re.search(r'dn\s*(\d+)', query_lower)
    if not m:
        m = re.search(r'(\d+)\s*mm', query_lower)
    return int(m.group(1)) if m else None


def register_bim_query_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register bim_query NL search tool."""

    @mcp_server.tool()
    async def bim_query(
        query: str,
        colorize: bool = False,
        limit: int = 100,
        ctx: Context = None,
    ) -> dict:
        """Search BIM elements using natural language query in Russian or English.

        Examples:
        - "газобетонные стены на 3 этаже"
        - "все двери на уровне 1"
        - "монолитные колонны выше 5 метров"
        - "трубы ГВС диаметром 50мм"

        Parses the query against semantic patterns and calls bim_search automatically.
        """
        patterns = _load_patterns()
        if not patterns:
            return {"error": "Could not load global_patterns.json", "path": PATTERNS_PATH}

        reverse_index = _build_reverse_index(patterns)
        query_lower = query.lower().strip()

        # --- Extract category ---
        category = _extract_category_from_query(query_lower)

        # --- Semantic pattern match ---
        pattern_id = _match_vor_name_to_pattern(query_lower, reverse_index)
        keywords = []
        matched_pattern = None
        if pattern_id:
            matched_pattern = next((p for p in patterns if p.get('id') == pattern_id), None)
            if matched_pattern:
                keywords = matched_pattern.get('keywords', [])[:5]

        # --- Extract structural filters from query ---
        level_filter = _extract_level_from_query(query_lower)
        height_op, height_val = _extract_height_filter(query_lower)
        diameter = _extract_diameter_filter(query_lower)

        # --- Build filters list ---
        filters = []

        # Keyword filter on type_name (use longest keyword from pattern)
        if keywords:
            best_kw = max(keywords, key=len)
            filters.append({"param": "type_name", "op": "contains", "value": best_kw})

        # Level filter
        if level_filter:
            filters.append({"param": "level", "op": "contains", "value": level_filter})

        # Height filter (uses 'length' as proxy for height in some categories)
        if height_op and height_val is not None:
            filters.append({"param": "length", "op": height_op, "value": height_val})

        # Diameter filter for pipes (type_name contains diameter string)
        if diameter and category == 'Pipes':
            filters.append({
                "param": "type_name", "op": "contains",
                "value": str(diameter)
            })

        # Build and execute search code
        code = _build_search_code(category, filters, None, limit)
        resp = await revit_post("/execute_code/", {"code": code}, ctx)

        results = {}
        if isinstance(resp, dict) and resp.get("status") == "success":
            raw = resp.get("output", "{}").strip()
            try:
                results = json.loads(raw)
            except Exception as e:
                results = {"error": "Parse failed: " + str(e), "raw": raw[:400]}
        else:
            results = {"error": str(resp)}

        return {
            "query": query,
            "interpreted": {
                "category":   category,
                "pattern_id": pattern_id,
                "pattern_label": matched_pattern.get("label") if matched_pattern else None,
                "filters":    filters,
                "level":      level_filter,
                "height":     {"op": height_op, "value": height_val} if height_op else None,
                "diameter_mm": diameter,
            },
            "results": results,
        }
