# -*- coding: utf-8 -*-
"""BIM Query — natural-language search for BIM elements via semantic patterns."""
import json
import logging
import os
import re
from mcp.server.fastmcp import Context

logger = logging.getLogger(__name__)

# In-memory cache: query_string -> AI interpretation dict
_AI_CACHE: dict = {}

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


# ---------------------------------------------------------------------------
# AI interpretation layer (GPT-4o-mini structured extraction)
# ---------------------------------------------------------------------------

async def _ai_interpret_query(query: str) -> dict:
    """Use OpenAI GPT-4o-mini to extract structured BIM intent from NL query.

    Returns dict: {category, level_filter, keywords, intent, confidence}.
    Returns None if API key missing or call fails (triggers keyword fallback).
    Uses in-memory cache to avoid redundant API calls.
    """
    # Check cache first
    cache_key = query.strip().lower()
    if cache_key in _AI_CACHE:
        logger.debug("AI cache hit for query: %r", query)
        return _AI_CACHE[cache_key]

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        key_file = os.path.join(os.path.dirname(__file__), "..", ".openai_key")
        if os.path.exists(key_file):
            with open(key_file, "r", encoding="utf-8") as fk:
                api_key = fk.read().strip()
    if not api_key:
        return None  # no key → keyword fallback

    try:
        import openai  # optional dep; already in project env
        client = openai.AsyncOpenAI(api_key=api_key)

        system_msg = (
            "You are a BIM assistant. Extract structured info from queries about "
            "building elements. Categories (use exact name): Walls/Floors/Roofs/"
            "Doors/Windows/Stairs/Ramps/Ceilings/StructuralColumns/StructuralFraming/"
            "StructuralFoundation/Pipes/Ducts/CableTray/Furniture/"
            "MechanicalEquipment/LightingFixtures/ElectricalEquipment/Rooms. "
            "Respond ONLY with valid JSON matching the schema."
        )

        schema = {
            "type": "object",
            "properties": {
                "category":     {"type": "string"},
                "level_filter": {"type": "string"},
                "keywords":     {"type": "array", "items": {"type": "string"}},
                "intent":       {"type": "string", "enum": ["list", "count", "volume", "filter"]},
                "confidence":   {"type": "number"},
            },
            "required": ["category", "level_filter", "keywords", "intent", "confidence"],
            "additionalProperties": False,
        }

        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user",   "content": "Query: " + query},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "bim_query_interpretation",
                    "strict": True,
                    "schema": schema,
                },
            },
            temperature=0,
            max_tokens=256,
        )
        result = json.loads(resp.choices[0].message.content)
        _AI_CACHE[cache_key] = result  # store in cache
        return result
    except Exception as exc:
        logger.warning("AI interpretation failed: %s", exc)
        return None  # any failure → keyword fallback


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

        query_lower = query.lower().strip()

        # --- Try AI interpretation first ---
        ai_result = await _ai_interpret_query(query)
        interpreted_by = "keyword"

        if ai_result and ai_result.get("category"):
            # AI succeeded — use its category and level
            category = ai_result["category"]
            level_filter = ai_result.get("level_filter", "")
            ai_keywords = ai_result.get("keywords", [])
            interpreted_by = "ai"
            logger.info(
                "AI interpreted: category=%s, level=%r, intent=%s, confidence=%.2f",
                category, level_filter,
                ai_result.get("intent", "?"),
                ai_result.get("confidence", 0.0),
            )
        else:
            # Keyword fallback
            category = _extract_category_from_query(query_lower)
            logger.info("Keyword fallback: category=%s", category)
            level_filter = _extract_level_from_query(query_lower)
            ai_keywords = []

        # --- Semantic pattern match (always run for extra keywords) ---
        pattern_id = _match_vor_name_to_pattern(query_lower, patterns)
        keywords = ai_keywords
        matched_pattern = None
        if pattern_id:
            matched_pattern = next((p for p in patterns if p.get('id') == pattern_id), None)
            if matched_pattern and not keywords:
                keywords = matched_pattern.get('keywords', [])[:5]

        # --- Extract structural filters (height/diameter always from regex) ---
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
                "category":      category,
                "pattern_id":    pattern_id,
                "pattern_label": matched_pattern.get("label") if matched_pattern else None,
                "filters":       filters,
                "level":         level_filter,
                "height":        {"op": height_op, "value": height_val} if height_op else None,
                "diameter_mm":   diameter,
                "interpreted_by": interpreted_by,
                "ai_confidence": ai_result.get("confidence") if ai_result else None,
            },
            "results": results,
        }
