# -*- coding: utf-8 -*-
"""Helpers for working with Revit linked files (.rvt).

Provides IronPython code builders that are executed inside Revit via /execute_code/.
All string generation avoids f-strings (uses concatenation) for IronPython compatibility.
"""
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M


def build_linked_files_code():
    """Returns IronPython code that discovers all loaded linked documents.

    The generated code prints a JSON list:
    [{"name": str, "loaded": bool, "path": str, "element_count": int}, ...]
    """
    return (
        "import json\n"
        "results = []\n"
        "links = DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements()\n"
        "for link in links:\n"
        "    link_doc = link.GetLinkDocument()\n"
        "    if link_doc is None:\n"
        "        results.append({'name': link.Name, 'loaded': False, 'path': '', 'element_count': 0})\n"
        "        continue\n"
        "    results.append({\n"
        "        'name': link_doc.Title,\n"
        "        'loaded': True,\n"
        "        'path': link_doc.PathName,\n"
        "        'element_count': DB.FilteredElementCollector(link_doc).WhereElementIsNotElementType().GetElementCount()\n"
        "    })\n"
        "print(json.dumps(results))\n"
    )


def build_linked_batch_code(batch_cats, link_title):
    """Returns IronPython code that scans a batch of categories in a specific linked document.

    Output format matches _scan_engine._build_batch_code for compatibility with
    _build_summary_from_catalog and bim_catalog consumers:
    {CategoryName: {total_count, total_volume_m3, total_area_m2, total_length_m, types: [...]}}

    Args:
        batch_cats: list of category name strings (keys of CATEGORY_REGISTRY)
        link_title: str — the Title of the linked Revit document to scan
    """
    lines = [
        "import json",
        "FT3_TO_M3 = " + repr(FT3_TO_M3),
        "FT2_TO_M2 = " + repr(FT2_TO_M2),
        "FT_TO_M   = " + repr(FT_TO_M),
        "target_title = " + repr(link_title),
        "result = {}",
        "",
        "# Find the linked document by title",
        "link_doc = None",
        "for _link in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements():",
        "    _ld = _link.GetLinkDocument()",
        "    if _ld is not None and _ld.Title == target_title:",
        "        link_doc = _ld",
        "        break",
        "",
        "if link_doc is None:",
        "    print(json.dumps({'_error': 'Link not found: ' + target_title}))",
        "else:",
        "    CAT_MAP = {",
    ]

    for name in batch_cats:
        if name not in CATEGORY_REGISTRY:
            continue
        info = CATEGORY_REGISTRY[name]
        lines.append(
            "        '{}': (DB.BuiltInCategory.{}, {}, {}, {}),".format(
                name,
                info["ost"],
                "True" if info["has_volume"] else "False",
                "True" if info["has_area"] else "False",
                "True" if info["has_length"] else "False",
            )
        )

    lines += [
        "    }",
        "    for cat_name, (bic, has_vol, has_area, has_len) in CAT_MAP.items():",
        "        try:",
        "            elems = DB.FilteredElementCollector(link_doc).OfCategory(bic).WhereElementIsNotElementType().ToElements()",
        "            groups = {}",
        "            for elem in elems:",
        "                try:",
        "                    te = link_doc.GetElement(elem.GetTypeId())",
        "                    key = getattr(te, 'Name', None) or 'Unknown'",
        "                    vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)",
        "                    ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)",
        "                    lp = elem.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)",
        "                    vol   = vp.AsDouble() * FT3_TO_M3 if (vp and vp.HasValue and has_vol)  else 0.0",
        "                    area  = ap.AsDouble() * FT2_TO_M2 if (ap and ap.HasValue and has_area) else 0.0",
        "                    length= lp.AsDouble() * FT_TO_M   if (lp and lp.HasValue and has_len)  else 0.0",
        "                    if key not in groups:",
        "                        groups[key] = {'name': key, 'count': 0, 'volume_m3': 0.0, 'area_m2': 0.0, 'length_m': 0.0, 'type_id': te.Id.IntegerValue if te else 0}",
        "                    groups[key]['count']     += 1",
        "                    groups[key]['volume_m3'] += vol",
        "                    groups[key]['area_m2']   += area",
        "                    groups[key]['length_m']  += length",
        "                except: pass",
        "            if groups:",
        "                types_list = []",
        "                for v in groups.values():",
        "                    types_list.append({'name': v['name'], 'count': v['count'],",
        "                        'volume_m3': round(v['volume_m3'], 3),",
        "                        'area_m2':   round(v['area_m2'],   3),",
        "                        'length_m':  round(v['length_m'],  3),",
        "                        'type_id':   v['type_id']})",
        "                total_count = sum(t['count'] for t in types_list)",
        "                result[cat_name] = {",
        "                    'total_count':     total_count,",
        "                    'total_volume_m3': round(sum(t['volume_m3'] for t in types_list), 3),",
        "                    'total_area_m2':   round(sum(t['area_m2']   for t in types_list), 3),",
        "                    'total_length_m':  round(sum(t['length_m']  for t in types_list), 3),",
        "                    'types': sorted(types_list, key=lambda x: -x['count'])",
        "                }",
        "        except: pass",
        "    print(json.dumps(result))",
    ]

    return "\n".join(lines)
