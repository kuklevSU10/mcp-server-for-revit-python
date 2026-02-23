# -*- coding: utf-8 -*-
"""BIM volumes extraction tool for tender analysis."""
import json
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M


def register_bim_volumes_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM volume extraction tools."""

    @mcp_server.tool()
    async def bim_volumes(
        categories: list[str] = None,
        group_by: str = "type",
        ctx: Context = None,
    ) -> dict:
        """Extract volumes from BIM model grouped by category.

        categories: Walls, Floors, Roofs, Columns, Doors, Windows
        group_by: type | level
        Returns: {category: [{name, count, volume_m3, area_m2}]}
        """
        if categories is None:
            categories = ["Walls", "Floors", "Roofs"]

        cats_repr = repr(categories)
        group_repr = repr(group_by)

        code = (
            "import json\n"
            "CAT_MAP = {\n"
            "    'Walls': DB.BuiltInCategory.OST_Walls,\n"
            "    'Floors': DB.BuiltInCategory.OST_Floors,\n"
            "    'Roofs': DB.BuiltInCategory.OST_Roofs,\n"
            "    'Columns': DB.BuiltInCategory.OST_StructuralColumns,\n"
            "    'Doors': DB.BuiltInCategory.OST_Doors,\n"
            "    'Windows': DB.BuiltInCategory.OST_Windows,\n"
            "}\n"
            "categories = " + cats_repr + "\n"
            "group_by = " + group_repr + "\n"
            "FT3_TO_M3 = 0.028316846592\n"
            "FT2_TO_M2 = 0.09290304\n"
            "result = {}\n"
            "for cat_name in categories:\n"
            "    if cat_name not in CAT_MAP:\n"
            "        continue\n"
            "    bic = CAT_MAP[cat_name]\n"
            "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
            ".WhereElementIsNotElementType().ToElements()\n"
            "    groups = {}\n"
            "    for elem in elems:\n"
            "        if group_by == 'level':\n"
            "            lvl = doc.GetElement(elem.LevelId) "
            "if hasattr(elem, 'LevelId') else None\n"
            "            key = lvl.Name if lvl else 'No Level'\n"
            "        else:\n"
            "            te = doc.GetElement(elem.GetTypeId())\n"
            "            key = te.Name if te else 'Unknown'\n"
            "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
            "        ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)\n"
            "        vol = vp.AsDouble() if vp and vp.HasValue else 0.0\n"
            "        area = ap.AsDouble() if ap and ap.HasValue else 0.0\n"
            "        if key not in groups:\n"
            "            groups[key] = {'name': key, 'count': 0,"
            " 'volume_m3': 0.0, 'area_m2': 0.0}\n"
            "        groups[key]['count'] += 1\n"
            "        groups[key]['volume_m3'] += vol * FT3_TO_M3\n"
            "        groups[key]['area_m2'] += area * FT2_TO_M2\n"
            "    result[cat_name] = [{'name': v['name'], 'count': v['count'],"
            " 'volume_m3': round(v['volume_m3'], 3),"
            " 'area_m2': round(v['area_m2'], 3)} for v in groups.values()]\n"
            "print(json.dumps(result))\n"
        )

        response = await revit_post("/execute_code/", {"code": code}, ctx)
        if isinstance(response, dict) and response.get("status") == "success":
            output = response.get("output", "{}").strip()
            try:
                return json.loads(output)
            except Exception as e:
                return {"error": "Parse failed: {}".format(str(e)), "raw": output}
        return {"error": str(response)}
