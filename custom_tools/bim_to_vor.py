# DEPRECATED: используй vor_vs_bim вместо этого инструмента.
# -*- coding: utf-8 -*-
"""BIM to VOR (work breakdown) mapping tool."""
import json
import os
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M, ironpython_cat_map, CAT_OST_MAP

_MAPPINGS_DIR = os.path.join(os.path.dirname(__file__), "mappings")


def _load_mapping(name: str) -> dict:
    path = os.path.join(_MAPPINGS_DIR, "{}_mapping.json".format(name))
    if not os.path.exists(path):
        raise FileNotFoundError("Mapping not found: {}".format(path))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def register_bim_to_vor_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM-to-VOR mapping tools."""

    @mcp_server.tool()
    async def bim_to_vor(
        mapping: str = "default",
        ctx: Context = None,
    ) -> dict:
        """Map BIM model volumes to VOR (work breakdown) positions.

        mapping: name of mapping file in custom_tools/mappings/ (without _mapping.json)
        Returns: {positions: [{vor_id, name, unit, volume, source}]}
        """
        try:
            mapping_data = _load_mapping(mapping)
        except FileNotFoundError as e:
            return {"error": str(e)}

        positions_cfg = mapping_data.get("positions", [])
        needed_cats = list({
            p["bim_category"]
            for p in positions_cfg
            if p.get("bim_category")
        })

        if not needed_cats:
            return {"positions": [], "note": "No BIM categories in mapping"}

        cats_repr = repr(needed_cats)
        code = (
            "import json\n"
            + ironpython_cat_map(list(CAT_OST_MAP.keys())) + "\n"
            "FT3_TO_M3 = 0.028316846592\n"
            "FT2_TO_M2 = 0.09290304\n"
            "categories = " + cats_repr + "\n"
            "result = {}\n"
            "for cat_name in categories:\n"
            "    if cat_name not in CAT_MAP:\n"
            "        continue\n"
            "    bic = CAT_MAP[cat_name]\n"
            "    elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
            ".WhereElementIsNotElementType().ToElements()\n"
            "    totals = {'count': 0, 'volume_m3': 0.0, 'area_m2': 0.0, 'types': []}\n"
            "    for elem in elems:\n"
            "        te = doc.GetElement(elem.GetTypeId())\n"
            "        type_name = te.Name if te else ''\n"
            "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
            "        ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)\n"
            "        totals['volume_m3'] += (vp.AsDouble() if vp and vp.HasValue else 0.0)"
            " * FT3_TO_M3\n"
            "        totals['area_m2'] += (ap.AsDouble() if ap and ap.HasValue else 0.0)"
            " * FT2_TO_M2\n"
            "        totals['count'] += 1\n"
            "        if type_name and type_name not in totals['types']:\n"
            "            totals['types'].append(type_name)\n"
            "    result[cat_name] = totals\n"
            "print(json.dumps(result))\n"
        )

        response = await revit_post("/execute_code/", {"code": code}, ctx)
        bim_data = {}
        if isinstance(response, dict) and response.get("status") == "success":
            try:
                bim_data = json.loads(response.get("output", "{}").strip())
            except Exception:
                pass

        positions = []
        for pos in positions_cfg:
            cat = pos.get("bim_category")
            bim_filter = pos.get("bim_filter") or {}
            use_area = pos.get("use_area", False)
            use_count = pos.get("use_count", False)
            manual = pos.get("manual_volume")

            if cat and cat in bim_data:
                cat_data = bim_data[cat]
                if use_count:
                    volume = cat_data.get("count", 0)
                elif use_area:
                    volume = round(cat_data.get("area_m2", 0.0), 3)
                else:
                    volume = round(cat_data.get("volume_m3", 0.0), 3)
                source = "BIM:{}".format(cat)
                if bim_filter.get("type_contains"):
                    source += " (filter:approx)"
            elif manual is not None:
                volume = manual
                source = "manual"
            else:
                volume = None
                source = "missing"

            positions.append({
                "vor_id": pos.get("vor_id"),
                "name": pos.get("name"),
                "unit": pos.get("unit"),
                "volume": volume,
                "source": source,
            })

        return {"positions": positions, "mapping": mapping}
