# -*- coding: utf-8 -*-
"""BIM model audit tool — checks for common modeling issues."""
import json
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M

_ZERO_VOLUME_CODE = (
    "import json\n"
    "CAT_MAP = {\n"
    "    'Walls': DB.BuiltInCategory.OST_Walls,\n"
    "    'Floors': DB.BuiltInCategory.OST_Floors,\n"
    "    'Roofs': DB.BuiltInCategory.OST_Roofs,\n"
    "    'Columns': DB.BuiltInCategory.OST_StructuralColumns,\n"
    "}\n"
    "issues = []\n"
    "for cat_name, bic in CAT_MAP.items():\n"
    "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
    ".WhereElementIsNotElementType().ToElements()\n"
    "    for elem in elems:\n"
    "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
    "        vol = vp.AsDouble() if vp and vp.HasValue else -1\n"
    "        if vol <= 0:\n"
    "            issues.append({'type': 'zero_volume', 'category': cat_name,"
    " 'element_id': elem.Id.IntegerValue,"
    " 'description': 'Element has zero or no volume computed'})\n"
    "print(json.dumps(issues))\n"
)

_MISSING_LEVEL_CODE = (
    "import json\n"
    "ALL_CATS = [\n"
    "    DB.BuiltInCategory.OST_Walls, DB.BuiltInCategory.OST_Floors,\n"
    "    DB.BuiltInCategory.OST_Roofs, DB.BuiltInCategory.OST_Doors,\n"
    "    DB.BuiltInCategory.OST_Windows,\n"
    "]\n"
    "issues = []\n"
    "for bic in ALL_CATS:\n"
    "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
    ".WhereElementIsNotElementType().ToElements()\n"
    "    for elem in elems:\n"
    "        has_level = hasattr(elem, 'LevelId') and "
    "elem.LevelId != DB.ElementId.InvalidElementId\n"
    "        if not has_level:\n"
    "            cat = elem.Category.Name if elem.Category else 'Unknown'\n"
    "            issues.append({'type': 'missing_level', 'category': cat,"
    " 'element_id': elem.Id.IntegerValue,"
    " 'description': 'Element has no associated level'})\n"
    "print(json.dumps(issues))\n"
)

_DUPLICATE_CODE = (
    "import json\n"
    "AUDIT_CATS = [\n"
    "    DB.BuiltInCategory.OST_Walls,\n"
    "    DB.BuiltInCategory.OST_Floors,\n"
    "    DB.BuiltInCategory.OST_StructuralColumns,\n"
    "    DB.BuiltInCategory.OST_StructuralFraming,\n"
    "]\n"
    "seen = {}\n"
    "issues = []\n"
    "for bic in AUDIT_CATS:\n"
    "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
    ".WhereElementIsNotElementType().ToElements()\n"
    "    for elem in elems:\n"
    "        if not elem.Location:\n"
    "            continue\n"
    "        type_id = elem.GetTypeId().IntegerValue\n"
    "        loc = elem.Location\n"
    "        key = None\n"
    "        if hasattr(loc, 'Point'):\n"
    "            pt = loc.Point\n"
    "            key = (type_id, round(pt.X, 2), round(pt.Y, 2), round(pt.Z, 2))\n"
    "        if key:\n"
    "            if key in seen:\n"
    "                issues.append({'type': 'duplicate_elements',"
    " 'element_id': elem.Id.IntegerValue,"
    " 'duplicate_of': seen[key],"
    " 'description': 'Possible duplicate element at same location and type'})\n"
    "            else:\n"
    "                seen[key] = elem.Id.IntegerValue\n"
    "print(json.dumps(issues[:200]))\n"
)


_MISSING_PARAMS_CODE = (
    "import json\n"
    "AUDIT_CATS = [\n"
    "    DB.BuiltInCategory.OST_Walls,\n"
    "    DB.BuiltInCategory.OST_Doors,\n"
    "    DB.BuiltInCategory.OST_Windows,\n"
    "    DB.BuiltInCategory.OST_StructuralColumns,\n"
    "    DB.BuiltInCategory.OST_StructuralFraming,\n"
    "]\n"
    "issues = []\n"
    "CHECKED_PARAMS = [\n"
    "    DB.BuiltInParameter.ALL_MODEL_MARK,\n"
    "]\n"
    "for bic in AUDIT_CATS:\n"
    "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
    ".WhereElementIsNotElementType().ToElements()\n"
    "    cat_name = ''\n"
    "    for elem in elems:\n"
    "        if not cat_name and elem.Category:\n"
    "            cat_name = elem.Category.Name\n"
    "        empty_params = []\n"
    "        for bip in CHECKED_PARAMS:\n"
    "            try:\n"
    "                p = elem.get_Parameter(bip)\n"
    "                if p and not p.AsString():\n"
    "                    empty_params.append(str(bip).split('.')[-1])\n"
    "            except:\n"
    "                pass\n"
    "        if empty_params:\n"
    "            issues.append({'type': 'missing_params', 'category': cat_name,"
    " 'element_id': elem.Id.IntegerValue,"
    " 'missing': empty_params,"
    " 'description': 'Element missing required parameter values: ' + ', '.join(empty_params)})\n"
    "        if len(issues) >= 500:\n"
    "            break\n"
    "print(json.dumps(issues[:500]))\n"
)

_UNUSED_FAMILIES_CODE = (
    "import json\n"
    "# Get all placed family instances\n"
    "placed_symbols = set()\n"
    "all_instances = DB.FilteredElementCollector(doc)"
    ".OfClass(DB.FamilyInstance).ToElements()\n"
    "for inst in all_instances:\n"
    "    placed_symbols.add(inst.GetTypeId().IntegerValue)\n"
    "# Get all loaded family symbols\n"
    "issues = []\n"
    "all_families = DB.FilteredElementCollector(doc)"
    ".OfClass(DB.Family).ToElements()\n"
    "for fam in all_families:\n"
    "    if fam.IsEditable:\n"
    "        sym_ids = list(fam.GetFamilySymbolIds())\n"
    "        any_placed = any(sid.IntegerValue in placed_symbols for sid in sym_ids)\n"
    "        if not any_placed and sym_ids:\n"
    "            issues.append({'type': 'unused_family',"
    " 'element_id': fam.Id.IntegerValue,"
    " 'family_name': fam.Name,"
    " 'symbol_count': len(sym_ids),"
    " 'description': 'Family loaded but has no placed instances: ' + fam.Name})\n"
    "print(json.dumps(issues[:200]))\n"
)


def register_bim_audit_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM audit tools."""

    @mcp_server.tool()
    async def bim_audit(
        checks: list[str] = None,
        ctx: Context = None,
    ) -> dict:
        """Audit BIM model for common issues.

        checks: zero_volume, missing_level, duplicate_elements, missing_params, unused_families, all
        Returns: {issues: [{type, description, element_id, severity}], summary}
        """
        if checks is None:
            checks = ["all"]

        run_all = "all" in checks
        all_issues = []

        async def run_check(code, check_name):
            resp = await revit_post("/execute_code/", {"code": code}, ctx)
            if isinstance(resp, dict) and resp.get("status") == "success":
                try:
                    items = json.loads(resp.get("output", "[]").strip())
                    for item in items:
                        item.setdefault("severity", "warning")
                    return items
                except Exception as e:
                    return [{"type": "audit_error", "description": str(e),
                             "element_id": None, "severity": "error"}]
            return []

        if run_all or "zero_volume" in checks:
            found = await run_check(_ZERO_VOLUME_CODE, "zero_volume")
            all_issues.extend(found)

        if run_all or "missing_level" in checks:
            found = await run_check(_MISSING_LEVEL_CODE, "missing_level")
            all_issues.extend(found)

        if run_all or "duplicate_elements" in checks:
            found = await run_check(_DUPLICATE_CODE, "duplicate_elements")
            all_issues.extend(found)

        if run_all or "missing_params" in checks:
            found = await run_check(_MISSING_PARAMS_CODE, "missing_params")
            all_issues.extend(found)

        if run_all or "unused_families" in checks:
            found = await run_check(_UNUSED_FAMILIES_CODE, "unused_families")
            all_issues.extend(found)

        by_type: dict[str, int] = {}
        for issue in all_issues:
            t = issue.get("type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "issues": all_issues,
            "summary": {
                "total_issues": len(all_issues),
                "by_type": by_type,
                "checks_run": checks,
            },
        }
