# -*- coding: utf-8 -*-
"""Helpers for working with Revit linked files (.rvt).

Provides IronPython code builders that are executed inside Revit via /execute_code/.
All string generation avoids f-strings (uses concatenation) for IronPython compatibility.
"""
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M
from ._scan_engine import _build_batch_code


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
    # Convert CATEGORY_REGISTRY dict format to the tuple format expected by _build_batch_code.
    cat_map = {
        name: (info["ost"], info["has_volume"], info["has_area"], info["has_length"])
        for name, info in CATEGORY_REGISTRY.items()
    }

    # Prologue: declare constants, find the linked document by title, guard on missing link.
    prologue_lines = [
        "import json",
        "FT3_TO_M3 = " + repr(FT3_TO_M3),
        "FT2_TO_M2 = " + repr(FT2_TO_M2),
        "FT_TO_M = " + repr(FT_TO_M),
        "target_title = " + repr(link_title),
        "result = {}",
        "link_doc = None",
        "for _link in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements():",
        "    _ld = _link.GetLinkDocument()",
        "    if _ld is not None and _ld.Title == target_title:",
        "        link_doc = _ld",
        "        break",
        "if link_doc is None:",
        "    print(json.dumps({'_error': 'Link not found: ' + target_title}))",
        "else:",
    ]

    # Generate the core scan body via _build_batch_code, then indent it for the else-block.
    # Strip lines already emitted by the prologue (import json, constants, result = {}).
    _skip = {"import json", "FT3_TO_M3 = 0.028316846592", "FT2_TO_M2 = 0.09290304",
             "FT_TO_M = 0.3048", "result = {}"}
    scan_code = _build_batch_code(batch_cats, cat_map, include_params=False,
                                  doc_expression="link_doc")
    indented = []
    for line in scan_code.split("\n"):
        if line in _skip:
            continue
        indented.append("    " + line if line else "")

    return "\n".join(prologue_lines) + "\n" + "\n".join(indented)
