# -*- coding: utf-8 -*-
"""VOR vs BIM comparison tool — red-flag detection for tenders."""
import json
from mcp.server.fastmcp import Context


def register_vor_vs_bim_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register VOR vs BIM comparison tools."""

    @mcp_server.tool()
    async def vor_vs_bim(
        vor_data: str = "[]",
        tolerance: float = 3.0,
        ctx: Context = None,
    ) -> dict:
        """Compare client VOR volumes with BIM model.

        vor_data: JSON string with [{name, unit, volume}]
        tolerance: percentage threshold for red flags (default 3.0%)
        Returns: {matches, red_flags, missing_in_vor, summary}
        """
        try:
            vor_items = json.loads(vor_data)
        except Exception as e:
            return {"error": "Invalid vor_data JSON: {}".format(str(e))}

        if not isinstance(vor_items, list):
            return {"error": "vor_data must be a JSON array"}

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
            "FT3_TO_M3 = 0.0283168\n"
            "FT2_TO_M2 = 0.092903\n"
            "result = {}\n"
            "for cat_name, bic in CAT_MAP.items():\n"
            "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
            ".WhereElementIsNotElementType().ToElements()\n"
            "    vol_total = 0.0\n"
            "    area_total = 0.0\n"
            "    count = 0\n"
            "    for elem in elems:\n"
            "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
            "        ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)\n"
            "        vol_total += (vp.AsDouble() if vp and vp.HasValue else 0.0) * FT3_TO_M3\n"
            "        area_total += (ap.AsDouble() if ap and ap.HasValue else 0.0) * FT2_TO_M2\n"
            "        count += 1\n"
            "    result[cat_name] = {'volume_m3': round(vol_total, 3),"
            " 'area_m2': round(area_total, 3), 'count': count}\n"
            "print(json.dumps(result))\n"
        )

        response = await revit_post("/execute_code/", {"code": code}, ctx)
        bim_data = {}
        if isinstance(response, dict) and response.get("status") == "success":
            try:
                bim_data = json.loads(response.get("output", "{}").strip())
            except Exception:
                pass

        bim_totals = {
            "volume_m3": sum(v.get("volume_m3", 0) for v in bim_data.values()),
            "area_m2": sum(v.get("area_m2", 0) for v in bim_data.values()),
            "elements": sum(v.get("count", 0) for v in bim_data.values()),
        }

        matches = []
        red_flags = []
        vor_names = set()

        for item in vor_items:
            name = item.get("name", "")
            unit = item.get("unit", "")
            vor_vol = float(item.get("volume", 0) or 0)
            vor_names.add(name.lower())

            bim_vol = None
            for cat, cdata in bim_data.items():
                if cat.lower() in name.lower() or name.lower() in cat.lower():
                    if "m3" in unit or "м3" in unit:
                        bim_vol = cdata.get("volume_m3")
                    else:
                        bim_vol = cdata.get("area_m2")
                    break

            entry = {
                "name": name,
                "unit": unit,
                "vor_volume": vor_vol,
                "bim_volume": bim_vol,
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

        missing_in_vor = [
            {"category": cat, "bim_volume_m3": cdata.get("volume_m3"), "count": cdata.get("count")}
            for cat, cdata in bim_data.items()
            if cat.lower() not in vor_names and cdata.get("count", 0) > 0
        ]

        return {
            "matches": matches,
            "red_flags": red_flags,
            "missing_in_vor": missing_in_vor,
            "summary": {
                "total_vor_items": len(vor_items),
                "ok_count": len([m for m in matches if m.get("status") == "ok"]),
                "red_flag_count": len(red_flags),
                "no_match_count": len([m for m in matches if m.get("status") == "no_bim_match"]),
                "bim_totals": bim_totals,
                "tolerance_pct": tolerance,
            },
        }
