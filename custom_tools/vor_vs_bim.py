# -*- coding: utf-8 -*-
"""VOR vs BIM comparison — semantic matching via global_patterns.json."""
import json
import os
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2
from ._validation import validate_vor_data

PATTERNS_PATH = os.path.join(
    os.path.dirname(__file__),
    '..', '..', 'bim-semantic-layer', 'global_patterns.json'
)


def _load_patterns():
    """Load patterns list from global_patterns.json."""
    try:
        path = os.path.normpath(PATTERNS_PATH)
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get('patterns', [])
        return data
    except Exception:
        return []


def _build_reverse_index(patterns):
    """Build keyword (lowercase) -> pattern_id index.
    For overlapping keywords, higher priority pattern wins; then longer keyword.
    NOTE: This index does NOT handle negative_keywords — use _match_vor_name_to_pattern
    with patterns list directly for full semantic matching.
    """
    index = {}
    # Sort patterns by priority DESC so higher priority patterns register first
    sorted_patterns = sorted(patterns, key=lambda p: p.get('priority', 10), reverse=True)
    for p in sorted_patterns:
        pid = p.get('id', '')
        for kw in p.get('keywords', []):
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower not in index:
                index[kw_lower] = pid
    return index


def _match_vor_name_to_pattern(vor_name_lower, patterns):
    """Find best pattern for a VOR name using priority, negative_keywords, and keyword length.

    Args:
        vor_name_lower: lowercased VOR position name
        patterns: list of pattern dicts from global_patterns.json

    Returns:
        pattern_id (str) of best match, or None if no match found
    """
    candidates = []

    for p in patterns:
        pat_id = p.get('id', '')
        keywords = p.get('keywords', [])
        negative = p.get('negative_keywords', [])
        priority = p.get('priority', 10)

        # Skip pattern if any negative keyword matches
        if any(neg.lower() in vor_name_lower for neg in negative if neg):
            continue

        # Find the best (longest) matching keyword
        best_kw_len = 0
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower in vor_name_lower:
                if len(kw_lower) > best_kw_len:
                    best_kw_len = len(kw_lower)

        if best_kw_len > 0:
            candidates.append((priority, best_kw_len, pat_id))

    if not candidates:
        return None

    # Sort: priority DESC, then keyword length DESC
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _build_id_to_group(patterns):
    """Build pattern_id -> group string mapping."""
    return {p['id']: p.get('group', '') for p in patterns if 'id' in p}


def _build_id_to_unit(patterns):
    """Build pattern_id -> canonical unit (m3/m2/m/count) mapping."""
    return {p['id']: p.get('unit', 'count') for p in patterns if 'id' in p}


async def _fetch_bim_summary(revit_post, ctx):
    """Fetch bim_summary data (all semantic groups) from Revit model."""
    from ._constants import ALL_CATEGORIES, CAT_BATCHES
    from ._scan_engine import _build_batch_code
    from .bim_summary import _build_summary_from_catalog

    catalog_data = {}
    for batch in CAT_BATCHES:
        valid_batch = [c for c in batch if c in ALL_CATEGORIES]
        if not valid_batch:
            continue
        code = _build_batch_code(valid_batch, ALL_CATEGORIES, False)
        resp = await revit_post("/execute_code/", {"code": code}, ctx)
        if isinstance(resp, dict) and resp.get("status") == "success":
            raw = resp.get("output", "{}").strip()
            try:
                batch_result = json.loads(raw)
                catalog_data.update(batch_result)
            except Exception:
                pass

    if not catalog_data:
        return None

    patterns = _load_patterns()
    if not patterns:
        return None

    return _build_summary_from_catalog(catalog_data, patterns, "full")


def _extract_bim_vol_for_unit(bim_entry, vor_unit):
    """Pick correct volume value from bim_entry based on VOR unit string."""
    unit_lower = vor_unit.lower()
    if any(u in unit_lower for u in ('m3', 'м3', 'куб', 'кб.м', 'cubic')):
        return bim_entry.get('volume_m3', 0.0)
    if any(u in unit_lower for u in ('m2', 'м2', 'кв', 'sq', 'площ')):
        return bim_entry.get('area_m2', 0.0)
    if any(u in unit_lower for u in ('пог', 'п.м', 'lm', 'м пог')):
        return bim_entry.get('length_m', 0.0)
    # Fallback: use canonical unit from pattern
    pat_unit = bim_entry.get('pat_unit', 'count')
    if pat_unit == 'm3':
        return bim_entry.get('volume_m3', 0.0)
    if pat_unit == 'm2':
        return bim_entry.get('area_m2', 0.0)
    if pat_unit == 'm':
        return bim_entry.get('length_m', 0.0)
    return float(bim_entry.get('count', 0))


def register_vor_vs_bim_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register VOR vs BIM comparison tools with semantic matching."""

    @mcp_server.tool()
    async def vor_vs_bim(
        vor_data: str = "[]",
        tolerance: float = 3.0,
        ctx: Context = None,
    ) -> dict:
        """Compare client VOR volumes with BIM model using semantic matching.

        vor_data: JSON string: [{"name": "Кирпичная кладка", "unit": "м3", "volume": 456.7}, ...]
        tolerance: percentage threshold for red flags (default 3.0%)
        Returns: {matches, red_flags, missing_in_vor, summary}
        """
        # Validate before parsing
        err = validate_vor_data(vor_data)
        if err:
            return {"error": "Validation error: " + err}

        try:
            vor_items = json.loads(vor_data)
        except Exception as e:
            return {"error": "Invalid vor_data JSON: " + str(e)}

        if not isinstance(vor_items, list):
            return {"error": "vor_data must be a JSON array"}

        # Load semantic patterns
        patterns = _load_patterns()
        if not patterns:
            return {"error": "Could not load global_patterns.json", "path": PATTERNS_PATH}

        # Sort patterns by priority DESC once, for consistent matching
        patterns_sorted = sorted(patterns, key=lambda p: p.get('priority', 10), reverse=True)
        id_to_group = _build_id_to_group(patterns)
        id_to_unit = _build_id_to_unit(patterns)

        # Fetch BIM summary from Revit model
        summary = await _fetch_bim_summary(revit_post, ctx)
        if summary is None:
            return {"error": "Could not fetch BIM data from Revit"}

        # Build lookup: pattern_id -> bim_entry
        id_to_bim = {}
        for pid, group in id_to_group.items():
            parts = group.split(".", 1)
            top_key = parts[0]
            sub_key = parts[1] if len(parts) > 1 else "other"
            if top_key in summary and sub_key in summary[top_key]:
                grp = summary[top_key][sub_key]
                id_to_bim[pid] = {
                    "volume_m3": grp.get("total_volume_m3", 0.0),
                    "area_m2":   grp.get("total_area_m2",   0.0),
                    "length_m":  grp.get("total_length_m",  0.0),
                    "count":     grp.get("total_count",      0),
                    "label":     grp.get("label",           ""),
                    "pat_unit":  id_to_unit.get(pid, "count"),
                    "group":     group,
                    "bim_types": [b.get("type", "") for b in grp.get("breakdown", [])[:5]],
                }

        # Match VOR items to BIM semantic groups
        matches = []
        red_flags = []
        matched_patterns = set()

        for item in vor_items:
            name = item.get("name", "")
            vor_vol = float(item.get("volume", 0) or 0)
            unit = item.get("unit", "")
            name_lower = name.lower().strip()

            pattern_id = _match_vor_name_to_pattern(name_lower, patterns_sorted)
            bim_entry = id_to_bim.get(pattern_id) if pattern_id else None

            bim_vol = None
            if bim_entry is not None:
                bim_vol = _extract_bim_vol_for_unit(bim_entry, unit)
                matched_patterns.add(pattern_id)

            entry = {
                "name":            name,
                "unit":            unit,
                "vor_volume":      vor_vol,
                "bim_volume":      bim_vol,
                "matched_pattern": pattern_id,
                "bim_label":       bim_entry["label"] if bim_entry else None,
            }

            if bim_vol is None:
                entry["status"] = "no_bim_match"
                matches.append(entry)
            elif vor_vol == 0:
                entry["status"] = "zero_in_vor"
                entry["diff_pct"] = None
                red_flags.append(entry)
            else:
                diff_pct = abs(vor_vol - bim_vol) / vor_vol * 100
                entry["diff_pct"] = round(diff_pct, 2)
                if diff_pct > tolerance:
                    entry["status"] = "red_flag"
                    red_flags.append(entry)
                else:
                    entry["status"] = "ok"
                    matches.append(entry)

        # missing_in_vor: BIM patterns with volume but not mentioned in VOR
        missing_in_vor = []
        for pid, bim_entry in id_to_bim.items():
            if pid in matched_patterns:
                continue
            bim_vol_check = (
                bim_entry.get("volume_m3", 0) or
                bim_entry.get("area_m2", 0) or
                bim_entry.get("length_m", 0) or
                bim_entry.get("count", 0)
            )
            if bim_vol_check and bim_vol_check > 0:
                missing_in_vor.append({
                    "pattern_id":    pid,
                    "label":         bim_entry["label"],
                    "group":         bim_entry["group"],
                    "bim_volume_m3": bim_entry.get("volume_m3", 0),
                    "bim_area_m2":   bim_entry.get("area_m2",   0),
                    "bim_length_m":  bim_entry.get("length_m",  0),
                    "count":         bim_entry.get("count",     0),
                })

        missing_in_vor.sort(
            key=lambda x: -(x.get("bim_volume_m3") or x.get("bim_area_m2") or 0)
        )

        return {
            "matches":        matches,
            "red_flags":      red_flags,
            "missing_in_vor": missing_in_vor,
            "summary": {
                "total_vor":      len(vor_items),
                "ok":             len([m for m in matches if m.get("status") == "ok"]),
                "red_flags":      len(red_flags),
                "no_match":       len([m for m in matches if m.get("status") == "no_bim_match"]),
                "missing":        len(missing_in_vor),
                "tolerance_pct":  tolerance,
                "patterns_loaded": len(patterns),
            },
        }
