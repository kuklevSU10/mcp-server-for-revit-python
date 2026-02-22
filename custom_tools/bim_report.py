# -*- coding: utf-8 -*-
"""BIM report generator — produces Markdown tender report."""
import json
from datetime import datetime
from mcp.server.fastmcp import Context

_MODEL_INFO_CODE = (
    "import json\n"
    "info = {}\n"
    "info['title'] = doc.Title\n"
    "info['path'] = doc.PathName\n"
    "levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()\n"
    "info['level_count'] = len(list(levels))\n"
    "total = DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElements()\n"
    "info['element_count'] = len(list(total))\n"
    "print(json.dumps(info))\n"
)

_VOLUMES_CODE = (
    "import json\n"
    "CAT_MAP = {\n"
    "    'Walls': DB.BuiltInCategory.OST_Walls,\n"
    "    'Floors': DB.BuiltInCategory.OST_Floors,\n"
    "    'Roofs': DB.BuiltInCategory.OST_Roofs,\n"
    "    'Columns': DB.BuiltInCategory.OST_StructuralColumns,\n"
    "    'Doors': DB.BuiltInCategory.OST_Doors,\n"
    "    'Windows': DB.BuiltInCategory.OST_Windows,\n"
    "}\n"
    "FT3_TO_M3 = 0.0283168\n"
    "FT2_TO_M2 = 0.092903\n"
    "result = {}\n"
    "for cat_name, bic in CAT_MAP.items():\n"
    "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
    ".WhereElementIsNotElementType().ToElements()\n"
    "    vol = 0.0\n"
    "    area = 0.0\n"
    "    count = 0\n"
    "    for elem in elems:\n"
    "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
    "        ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)\n"
    "        vol += (vp.AsDouble() if vp and vp.HasValue else 0.0) * FT3_TO_M3\n"
    "        area += (ap.AsDouble() if ap and ap.HasValue else 0.0) * FT2_TO_M2\n"
    "        count += 1\n"
    "    result[cat_name] = {'count': count,"
    " 'volume_m3': round(vol, 2), 'area_m2': round(area, 2)}\n"
    "print(json.dumps(result))\n"
)

_LEVELS_CODE = (
    "import json\n"
    "levels = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()\n"
    "result = []\n"
    "for lvl in levels:\n"
    "    result.append({'name': lvl.Name,"
    " 'elevation_m': round(lvl.Elevation * 0.3048, 3)})\n"
    "result.sort(key=lambda x: x['elevation_m'])\n"
    "print(json.dumps(result))\n"
)


async def _fetch(revit_post, code, ctx):
    resp = await revit_post("/execute_code/", {"code": code}, ctx)
    if isinstance(resp, dict) and resp.get("status") == "success":
        try:
            return json.loads(resp.get("output", "null").strip())
        except Exception:
            pass
    return None


def register_bim_report_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM report generation tools."""

    @mcp_server.tool()
    async def bim_report(
        sections: list[str] = None,
        ctx: Context = None,
    ) -> str:
        """Generate BIM report for tender in Markdown format.

        sections: summary, volumes, levels, types, all
        Returns: Markdown string
        """
        if sections is None:
            sections = ["summary", "volumes"]

        run_all = "all" in sections
        parts = ["# BIM Model Report", "",
                 "_Generated: {}_".format(datetime.now().strftime("%Y-%m-%d %H:%M")), ""]

        if run_all or "summary" in sections:
            info = await _fetch(revit_post, _MODEL_INFO_CODE, ctx)
            parts.append("## Summary")
            if info:
                parts.append("| Field | Value |")
                parts.append("|---|---|")
                parts.append("| Document | {} |".format(info.get("title", "N/A")))
                parts.append("| Levels | {} |".format(info.get("level_count", "N/A")))
                parts.append("| Total elements | {} |".format(info.get("element_count", "N/A")))
            else:
                parts.append("_Could not retrieve model info._")
            parts.append("")

        if run_all or "volumes" in sections:
            vols = await _fetch(revit_post, _VOLUMES_CODE, ctx)
            parts.append("## Volumes by Category")
            if vols:
                parts.append("| Category | Count | Volume (m3) | Area (m2) |")
                parts.append("|---|---|---|---|")
                for cat, data in vols.items():
                    parts.append("| {} | {} | {} | {} |".format(
                        cat, data.get("count", 0),
                        data.get("volume_m3", 0), data.get("area_m2", 0)
                    ))
            else:
                parts.append("_Could not retrieve volume data._")
            parts.append("")

        if run_all or "levels" in sections:
            levels = await _fetch(revit_post, _LEVELS_CODE, ctx)
            parts.append("## Levels")
            if levels:
                parts.append("| Level | Elevation (m) |")
                parts.append("|---|---|")
                for lvl in levels:
                    parts.append("| {} | {} |".format(
                        lvl.get("name", ""), lvl.get("elevation_m", "")
                    ))
            else:
                parts.append("_Could not retrieve levels._")
            parts.append("")

        return "\n".join(parts)
