# -*- coding: utf-8 -*-
"""BIM model audit tool — checks for common modeling issues."""
import json
from mcp.server.fastmcp import Context

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
    "elems = DB.FilteredElementCollector(doc)"
    ".WhereElementIsNotElementType().ToElements()\n"
    "seen = {}\n"
    "issues = []\n"
    "for elem in elems:\n"
    "    if not elem.Location:\n"
    "        continue\n"
    "    type_id = elem.GetTypeId().IntegerValue\n"
    "    loc = elem.Location\n"
    "    key = None\n"
    "    if hasattr(loc, 'Point'):\n"
    "        pt = loc.Point\n"
    "        key = (type_id, round(pt.X, 2), round(pt.Y, 2), round(pt.Z, 2))\n"
    "    if key:\n"
    "        if key in seen:\n"
    "            issues.append({'type': 'duplicate_elements',"
    " 'element_id': elem.Id.IntegerValue,"
    " 'duplicate_of': seen[key],"
    " 'description': 'Possible duplicate element at same location and type'})\n"
    "        else:\n"
    "            seen[key] = elem.Id.IntegerValue\n"
    "print(json.dumps(issues[:50]))\n"
)


def register_bim_audit_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM audit tools."""

    @mcp_server.tool()
    async def bim_audit(
        checks: list[str] = None,
        ctx: Context = None,
    ) -> dict:
        """Audit BIM model for common issues.

        checks: zero_volume, missing_level, duplicate_elements, all
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
