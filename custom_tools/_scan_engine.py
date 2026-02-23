# -*- coding: utf-8 -*-
"""
_scan_engine.py — IronPython code-builder for batch category scanning.

Extracted from bim_catalog.py so that both bim_catalog and bim_summary
can import it without circular dependencies.
"""
from ._constants import FT3_TO_M3, FT2_TO_M2, FT_TO_M


def _build_batch_code(batch_cats, cat_map, include_params):
    """Build IronPython code to scan a batch of categories.

    Args:
        batch_cats: list of category name strings (keys of cat_map)
        cat_map:    dict  name -> (ost_name, has_vol, has_area, has_len)
        include_params: if True, collect sample type parameters

    Returns:
        str — IronPython source code to be executed in Revit context via /execute_code/
    """
    ip = "True" if include_params else "False"
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
    lines.append("        groups = {}")
    lines.append("        for elem in elems:")
    lines.append("            try:")
    lines.append("                te = doc.GetElement(elem.GetTypeId())")
    lines.append("                key = getattr(te, 'Name', None) or 'Unknown'")
    lines.append("                vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)")
    lines.append("                ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)")
    lines.append("                lp = elem.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)")
    lines.append("                vol = vp.AsDouble() * FT3_TO_M3 if (vp and vp.HasValue and has_vol) else 0.0")
    lines.append("                area = ap.AsDouble() * FT2_TO_M2 if (ap and ap.HasValue and has_area) else 0.0")
    lines.append("                length = lp.AsDouble() * FT_TO_M if (lp and lp.HasValue and has_len) else 0.0")
    lines.append("                if key not in groups:")
    lines.append("                    groups[key] = {'name': key, 'count': 0, 'volume_m3': 0.0, 'area_m2': 0.0, 'length_m': 0.0, 'type_id': te.Id.IntegerValue if te else 0}")
    lines.append("                groups[key]['count'] += 1")
    lines.append("                groups[key]['volume_m3'] += vol")
    lines.append("                groups[key]['area_m2'] += area")
    lines.append("                groups[key]['length_m'] += length")
    lines.append("                if " + ip + " and te:")
    lines.append("                    if 'sample_params' not in groups[key]:")
    lines.append("                        sp = {}")
    lines.append("                        for p in te.Parameters:")
    lines.append("                            try:")
    lines.append("                                if p and p.HasValue:")
    lines.append("                                    pn = p.Definition.Name")
    lines.append("                                    if p.StorageType.ToString() == 'Double':")
    lines.append("                                        sp[pn] = round(p.AsDouble(), 4)")
    lines.append("                                    elif p.StorageType.ToString() == 'String':")
    lines.append("                                        sv = p.AsString()")
    lines.append("                                        if sv: sp[pn] = sv")
    lines.append("                                    elif p.StorageType.ToString() == 'Integer':")
    lines.append("                                        sp[pn] = p.AsInteger()")
    lines.append("                            except: pass")
    lines.append("                        groups[key]['sample_params'] = sp")
    lines.append("            except: pass")
    lines.append("        if groups:")
    lines.append("            types_list = []")
    lines.append("            for v in groups.values():")
    lines.append("                t = {'name': v['name'], 'count': v['count'],")
    lines.append("                     'volume_m3': round(v['volume_m3'], 3),")
    lines.append("                     'area_m2': round(v['area_m2'], 3),")
    lines.append("                     'length_m': round(v['length_m'], 3),")
    lines.append("                     'type_id': v['type_id']}")
    lines.append("                if " + ip + " and 'sample_params' in v:")
    lines.append("                    t['sample_params'] = v['sample_params']")
    lines.append("                types_list.append(t)")
    lines.append("            total_count = sum(t['count'] for t in types_list)")
    lines.append("            result[cat_name] = {")
    lines.append("                'total_count': total_count,")
    lines.append("                'total_volume_m3': round(sum(t['volume_m3'] for t in types_list), 3),")
    lines.append("                'total_area_m2': round(sum(t['area_m2'] for t in types_list), 3),")
    lines.append("                'total_length_m': round(sum(t['length_m'] for t in types_list), 3),")
    lines.append("                'types': sorted(types_list, key=lambda x: -x['count'])")
    lines.append("            }")
    lines.append("    except: pass")
    lines.append("print(json.dumps(result))")
    return "\n".join(lines)
