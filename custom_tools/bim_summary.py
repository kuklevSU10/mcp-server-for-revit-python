# -*- coding: utf-8 -*-
"""BIM Summary — smart semantic summary of the entire BIM model."""
import json
import os
import re
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M
from ._linked_files import build_linked_files_code, build_linked_batch_code
from ._constants import MAX_BATCH_SIZE

PATTERNS_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "bim-semantic-layer", "global_patterns.json"
)


def _load_patterns():
    """Load global_patterns.json from bim-semantic-layer."""
    try:
        path = os.path.normpath(PATTERNS_PATH)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("patterns", [])
    except Exception as e:
        return []


def _match_type_to_pattern(type_name, category, patterns):
    """Match a type name + category to the best matching pattern.

    Uses priority (DESC), negative_keywords (exclusion), keyword and regex matching.
    Returns matched pattern dict, or None.
    """
    tn_lower = type_name.lower()
    candidates = []

    for pattern in patterns:
        # Check category filter
        allowed_cats = pattern.get("categories", [])
        if allowed_cats and category not in allowed_cats:
            continue

        # Skip if any negative keyword matches
        negative = pattern.get("negative_keywords", [])
        if any(neg.lower() in tn_lower for neg in negative if neg):
            continue

        priority = pattern.get("priority", 10)

        # Keyword match — find the longest matching keyword
        keywords = pattern.get("keywords", [])
        best_kw_len = 0
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and kw_lower in tn_lower:
                if len(kw_lower) > best_kw_len:
                    best_kw_len = len(kw_lower)

        if best_kw_len > 0:
            candidates.append((priority, best_kw_len, pattern))
            continue

        # Regex match (lower priority signal — use keyword length 0)
        for rex in pattern.get("regex", []):
            try:
                if re.search(rex, tn_lower):
                    candidates.append((priority, 0, pattern))
                    break
            except Exception:
                pass

    if not candidates:
        return None

    # Sort by priority DESC, then keyword length DESC
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return candidates[0][2]


def _group_key_from_pattern(pattern):
    """Return (group, label) from pattern."""
    return pattern["group"], pattern["label"]


def _build_summary_from_catalog(catalog_data, patterns, mode):
    """Match all catalog types to patterns and build semantic summary."""
    summary = {}
    unrecognized = []

    for cat_name, cat_data in catalog_data.items():
        if cat_name.startswith("_"):
            continue
        if not isinstance(cat_data, dict):
            continue
        types_list = cat_data.get("types", [])
        for tinfo in types_list:
            type_name = tinfo.get("name", "Unknown")
            count = tinfo.get("count", 0)
            volume_m3 = tinfo.get("volume_m3", 0.0)
            area_m2 = tinfo.get("area_m2", 0.0)
            length_m = tinfo.get("length_m", 0.0)

            pattern = _match_type_to_pattern(type_name, cat_name, patterns)

            if pattern is None:
                unrecognized.append({
                    "category": cat_name,
                    "type_name": type_name,
                    "count": count,
                    "volume_m3": volume_m3,
                    "area_m2": area_m2,
                })
                continue

            group = pattern["group"]
            label = pattern["label"]
            unit = pattern.get("unit", "count")

            # Apply mode filter
            if mode == "structural" and not group.startswith("structural"):
                continue
            if mode == "mep" and not group.startswith("mep"):
                continue
            if mode == "architectural" and not (
                group.startswith("architectural") or group.startswith("generic")
            ):
                continue

            # Build nested dict path from group (e.g. "structural.monolith" → summary["structural"]["monolith"])
            parts = group.split(".", 1)
            top_key = parts[0]
            sub_key = parts[1] if len(parts) > 1 else "other"

            if top_key not in summary:
                summary[top_key] = {}
            if sub_key not in summary[top_key]:
                summary[top_key][sub_key] = {
                    "label": label,
                    "total_count": 0,
                    "total_volume_m3": 0.0,
                    "total_area_m2": 0.0,
                    "total_length_m": 0.0,
                    "breakdown": [],
                }
            grp = summary[top_key][sub_key]
            grp["total_count"] += count
            grp["total_volume_m3"] = round(grp["total_volume_m3"] + volume_m3, 3)
            grp["total_area_m2"] = round(grp["total_area_m2"] + area_m2, 3)
            grp["total_length_m"] = round(grp["total_length_m"] + length_m, 3)
            grp["breakdown"].append({
                "category": cat_name,
                "type": type_name,
                "count": count,
                "volume_m3": volume_m3,
                "area_m2": area_m2,
                "length_m": length_m,
                "unit": unit,
            })

    # Sort breakdown by count descending
    for top_key in summary:
        for sub_key in summary[top_key]:
            summary[top_key][sub_key]["breakdown"].sort(
                key=lambda x: -x["count"]
            )

    # Add global stats
    result = dict(summary)
    result["_unrecognized"] = sorted(unrecognized, key=lambda x: -x["count"])
    result["_meta"] = {
        "patterns_loaded": len(patterns),
        "unrecognized_count": len(unrecognized),
        "mode": mode,
    }
    return result


def _tag_summary_source(summary, source):
    """Add source field to every breakdown item in a summary dict (in-place)."""
    for top_key, top_val in summary.items():
        if top_key.startswith("_") or not isinstance(top_val, dict):
            continue
        for sub_key, sub_val in top_val.items():
            if not isinstance(sub_val, dict):
                continue
            for item in sub_val.get("breakdown", []):
                item["source"] = source


def _merge_summary_into(base, extra):
    """Merge 'extra' summary into 'base' in-place (for include_links aggregation)."""
    for top_key, top_val in extra.items():
        if top_key.startswith("_") or not isinstance(top_val, dict):
            continue
        if top_key not in base:
            base[top_key] = {}
        for sub_key, sub_val in top_val.items():
            if not isinstance(sub_val, dict):
                continue
            if sub_key not in base[top_key]:
                base[top_key][sub_key] = {
                    "label": sub_val.get("label", sub_key),
                    "total_count": 0,
                    "total_volume_m3": 0.0,
                    "total_area_m2": 0.0,
                    "total_length_m": 0.0,
                    "breakdown": [],
                }
            grp = base[top_key][sub_key]
            grp["total_count"]     += sub_val.get("total_count", 0)
            grp["total_volume_m3"]  = round(grp["total_volume_m3"] + sub_val.get("total_volume_m3", 0.0), 3)
            grp["total_area_m2"]    = round(grp["total_area_m2"]   + sub_val.get("total_area_m2",   0.0), 3)
            grp["total_length_m"]   = round(grp["total_length_m"]  + sub_val.get("total_length_m",  0.0), 3)
            grp["breakdown"].extend(sub_val.get("breakdown", []))

    # Merge _unrecognized list
    if "_unrecognized" in extra:
        if "_unrecognized" not in base:
            base["_unrecognized"] = []
        base["_unrecognized"].extend(extra["_unrecognized"])


def _make_link_batches(size):
    """Yield batches of CATEGORY_REGISTRY keys, each of length <= size."""
    keys = list(CATEGORY_REGISTRY.keys())
    for i in range(0, len(keys), size):
        yield keys[i: i + size]




def _build_level_batch_code(batch_cats, cat_map):
    """Build IronPython code that scans categories and groups by (type_name, level_name).

    Returns JSON: {cat_name: {type_name: {level_name: {count, volume_m3, area_m2, length_m}}}}
    Note: no f-strings used (IronPython compatibility).
    """
    lines = [
        "import json",
        "FT3_TO_M3 = 0.028316846592",
        "FT2_TO_M2 = 0.09290304",
        "FT_TO_M = 0.3048",
        "result = {}",
        "CAT_MAP = {",
    ]
    for name in batch_cats:
        if name not in cat_map:
            continue
        ost, has_vol, has_area, has_len = cat_map[name]
        lines.append(
            "    '{}': (DB.BuiltInCategory.{}, {}, {}, {}),".format(
                name, ost,
                "True" if has_vol else "False",
                "True" if has_area else "False",
                "True" if has_len else "False",
            )
        )
    lines.append("}")
    lines.append("for cat_name, (bic, has_vol, has_area, has_len) in CAT_MAP.items():")
    lines.append("    try:")
    lines.append(
        "        elems = DB.FilteredElementCollector(doc)"
        ".OfCategory(bic).WhereElementIsNotElementType().ToElements()"
    )
    lines.append("        by_type = {}")
    lines.append("        for elem in elems:")
    lines.append("            try:")
    lines.append("                te = doc.GetElement(elem.GetTypeId())")
    lines.append("                type_name = getattr(te, 'Name', None) or 'Unknown'")
    # Level detection
    lines.append("                lp = elem.get_Parameter(DB.BuiltInParameter.LEVEL_PARAM)")
    lines.append("                if not lp or not lp.HasValue:")
    lines.append("                    lp = elem.get_Parameter(DB.BuiltInParameter.FAMILY_LEVEL_PARAM)")
    lines.append("                level_name = ''")
    lines.append("                if lp and lp.HasValue:")
    lines.append("                    level_el = doc.GetElement(lp.AsElementId())")
    lines.append("                    if level_el: level_name = level_el.Name")
    lines.append("                if not level_name:")
    lines.append("                    lvl_id = getattr(elem, 'LevelId', None)")
    lines.append("                    if lvl_id and lvl_id != DB.ElementId.InvalidElementId:")
    lines.append("                        lvl = doc.GetElement(lvl_id)")
    lines.append("                        if lvl: level_name = lvl.Name")
    lines.append("                if not level_name: level_name = 'Unknown'")
    # Volumes
    lines.append("                vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)")
    lines.append("                ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)")
    lines.append("                lcp = elem.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)")
    lines.append("                vol = vp.AsDouble() * FT3_TO_M3 if (vp and vp.HasValue and has_vol) else 0.0")
    lines.append("                area = ap.AsDouble() * FT2_TO_M2 if (ap and ap.HasValue and has_area) else 0.0")
    lines.append("                length = lcp.AsDouble() * FT_TO_M if (lcp and lcp.HasValue and has_len) else 0.0")
    # Accumulate
    lines.append("                if type_name not in by_type: by_type[type_name] = {}")
    lines.append("                if level_name not in by_type[type_name]:")
    lines.append("                    by_type[type_name][level_name] = {'count': 0, 'volume_m3': 0.0, 'area_m2': 0.0, 'length_m': 0.0}")
    lines.append("                by_type[type_name][level_name]['count'] += 1")
    lines.append("                by_type[type_name][level_name]['volume_m3'] = round(by_type[type_name][level_name]['volume_m3'] + vol, 3)")
    lines.append("                by_type[type_name][level_name]['area_m2'] = round(by_type[type_name][level_name]['area_m2'] + area, 3)")
    lines.append("                by_type[type_name][level_name]['length_m'] = round(by_type[type_name][level_name]['length_m'] + length, 3)")
    lines.append("            except: pass")
    lines.append("        result[cat_name] = by_type")
    lines.append("    except: pass")
    lines.append("print(json.dumps(result))")
    return "\n".join(lines)


def _add_level_data_to_summary(summary, level_catalog, patterns):
    """Enrich summary with by_level breakdown using level_catalog data.

    level_catalog: {cat_name: {type_name: {level_name: {count, volume_m3, ...}}}}
    Modifies summary in-place, adding 'by_level' key to each semantic group.
    """
    # Build pattern lookup: type_name + cat_name -> (top_key, sub_key)
    for cat_name, types_by_level in level_catalog.items():
        for type_name, levels in types_by_level.items():
            # Find which semantic group this type belongs to
            matched = _match_type_to_pattern(type_name, cat_name, patterns)
            if matched is None:
                continue
            group = matched["group"]
            parts = group.split(".", 1)
            top_key = parts[0]
            sub_key = parts[1] if len(parts) > 1 else "other"

            if top_key not in summary or sub_key not in summary[top_key]:
                continue

            grp = summary[top_key][sub_key]
            if "by_level" not in grp:
                grp["by_level"] = {}

            for level_name, lvl_data in levels.items():
                if level_name not in grp["by_level"]:
                    grp["by_level"][level_name] = {
                        "volume_m3": 0.0,
                        "area_m2":   0.0,
                        "length_m":  0.0,
                        "count":     0,
                    }
                entry = grp["by_level"][level_name]
                entry["count"]     += lvl_data.get("count",     0)
                entry["volume_m3"]  = round(entry["volume_m3"]  + lvl_data.get("volume_m3", 0.0), 3)
                entry["area_m2"]    = round(entry["area_m2"]    + lvl_data.get("area_m2",   0.0), 3)
                entry["length_m"]   = round(entry["length_m"]   + lvl_data.get("length_m",  0.0), 3)

    return summary

def register_bim_summary_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM summary tools."""

    @mcp_server.tool()
    async def bim_summary(
        mode: str = "full",
        include_links: bool = False,
        group_by_level: bool = False,
        ctx: Context = None,
    ) -> dict:
        """Smart semantic summary of the entire BIM model.

        mode: full / structural / mep / architectural
        include_links: if True, also scan all loaded linked .rvt files and merge results.
                       Each breakdown item will have a 'source' field ('host' or link title).
        group_by_level: if True, add per-level breakdown (by_level dict) to each semantic group.
        Uses global_patterns.json to group element types by construction meaning.
        Returns: {structural: {...}, architectural: {...}, mep: {...}, _unrecognized: [...]}
        """
        from ._constants import ALL_CATEGORIES, CAT_BATCHES
        from ._scan_engine import _build_batch_code

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
            return {"error": "Could not retrieve catalog data from Revit"}

        # Load patterns
        patterns = _load_patterns()
        if not patterns:
            return {
                "error": "Could not load global_patterns.json",
                "patterns_path": os.path.normpath(PATTERNS_PATH),
                "catalog_data": catalog_data,
            }

        host_summary = _build_summary_from_catalog(catalog_data, patterns, mode)

        if not include_links:
            if group_by_level:
                level_catalog = {}
                for batch in CAT_BATCHES:
                    valid_batch = [c for c in batch if c in ALL_CATEGORIES]
                    if not valid_batch:
                        continue
                    code = _build_level_batch_code(valid_batch, ALL_CATEGORIES)
                    resp = await revit_post("/execute_code/", {"code": code}, ctx)
                    if isinstance(resp, dict) and resp.get("status") == "success":
                        raw = resp.get("output", "{}").strip()
                        try:
                            batch_result = json.loads(raw)
                            level_catalog.update(batch_result)
                        except Exception:
                            pass
                if level_catalog:
                    host_summary = _add_level_data_to_summary(
                        host_summary, level_catalog, patterns
                    )
                else:
                    host_summary["_level_warning"] = "Could not fetch level data from Revit"
            return host_summary

        # --- Tag host breakdown items ---
        _tag_summary_source(host_summary, "host")

        # --- Discover linked files ---
        links_code = build_linked_files_code()
        links_resp = await revit_post("/execute_code/", {"code": links_code}, ctx)
        if not isinstance(links_resp, dict) or links_resp.get("status") != "success":
            host_summary["_links_error"] = "Could not retrieve linked files list"
            return host_summary

        links_raw = links_resp.get("output", "[]").strip()
        try:
            links_list = json.loads(links_raw)
        except Exception as e:
            host_summary["_links_error"] = "JSON parse error for links: " + str(e)
            return host_summary

        loaded_links = [lk for lk in links_list if lk.get("loaded")]
        host_summary["_meta"]["linked_files_found"] = len(links_list)
        host_summary["_meta"]["linked_files_loaded"] = len(loaded_links)

        # --- Scan each loaded linked file ---
        for link_info in loaded_links:
            link_title = link_info["name"]
            link_catalog = {}

            for batch in _make_link_batches(MAX_BATCH_SIZE):
                code = build_linked_batch_code(batch, link_title)
                resp = await revit_post("/execute_code/", {"code": code}, ctx)
                if not isinstance(resp, dict) or resp.get("status") != "success":
                    continue
                raw = resp.get("output", "{}").strip()
                try:
                    batch_result = json.loads(raw)
                    if "_error" not in batch_result:
                        link_catalog.update(batch_result)
                except Exception:
                    pass

            if not link_catalog:
                continue

            link_summary = _build_summary_from_catalog(link_catalog, patterns, mode)
            _tag_summary_source(link_summary, link_title)
            _merge_summary_into(host_summary, link_summary)

        # group_by_level enrichment (host model only, links not supported for level scan)
        if group_by_level:
            level_catalog = {}
            for batch in CAT_BATCHES:
                valid_batch = [c for c in batch if c in ALL_CATEGORIES]
                if not valid_batch:
                    continue
                code = _build_level_batch_code(valid_batch, ALL_CATEGORIES)
                resp = await revit_post("/execute_code/", {"code": code}, ctx)
                if isinstance(resp, dict) and resp.get("status") == "success":
                    raw = resp.get("output", "{}").strip()
                    try:
                        batch_result = json.loads(raw)
                        level_catalog.update(batch_result)
                    except Exception:
                        pass
            if level_catalog:
                host_summary = _add_level_data_to_summary(
                    host_summary, level_catalog, patterns
                )

        return host_summary
