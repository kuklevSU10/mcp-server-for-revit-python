# -*- coding: utf-8 -*-
"""BIM Search — find elements by parameters with multiple operators."""
import json
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M
from ._validation import validate_filters

CAT_MAP_SEARCH = {
    "Walls":                "OST_Walls",
    "Floors":               "OST_Floors",
    "Roofs":                "OST_Roofs",
    "Ceilings":             "OST_Ceilings",
    "Columns":              "OST_StructuralColumns",
    "StructuralFraming":    "OST_StructuralFraming",
    "StructuralFoundation": "OST_StructuralFoundation",
    "Doors":                "OST_Doors",
    "Windows":              "OST_Windows",
    "Furniture":            "OST_Furniture",
    "GenericModel":         "OST_GenericModel",
    "Ducts":                "OST_DuctCurves",
    "Pipes":                "OST_PipeCurves",
    "MechanicalEquipment":  "OST_MechanicalEquipment",
    "ElectricalEquipment":  "OST_ElectricalEquipment",
    "LightingFixtures":     "OST_LightingFixtures",
    "CableTray":            "OST_CableTray",
    "Conduit":              "OST_Conduit",
    "Ramps":                "OST_Ramps",
    "Stairs":               "OST_Stairs",
}

# Map op name → Python expression (v=value, pv=param_value string)
OP_MAP = {
    "contains":     "isinstance(pv, str) and v.lower() in pv.lower()",
    "not_contains": "not (isinstance(pv, str) and v.lower() in pv.lower())",
    "eq":           "str(pv).lower() == str(v).lower()",
    "neq":          "str(pv).lower() != str(v).lower()",
    "gt":           "(isinstance(pv, (int,float)) and pv > v)",
    "lt":           "(isinstance(pv, (int,float)) and pv < v)",
    "gte":          "(isinstance(pv, (int,float)) and pv >= v)",
    "lte":          "(isinstance(pv, (int,float)) and pv <= v)",
    "is_empty":     "(pv is None or pv == '' or pv == 0)",
    "not_empty":    "(pv is not None and pv != '' and pv != 0)",
}

SPECIAL_PARAMS = {"type_name", "level", "volume", "area", "width", "length"}

COLOR_MAP = {
    "red":    (255, 0, 0),
    "blue":   (0, 0, 255),
    "green":  (0, 200, 0),
    "yellow": (255, 255, 0),
    "orange": (255, 128, 0),
    "purple": (128, 0, 255),
}


def _build_search_code(category, filters, return_params, limit):
    ost = CAT_MAP_SEARCH.get(category, "OST_Walls")
    filters_repr = repr(filters)
    rp_repr = repr(return_params)
    lim = int(limit)

    code = (
        "import json\n"
        "FT3_TO_M3 = 0.028316846592\n"
        "FT2_TO_M2 = 0.09290304\n"
        "FT_TO_M = 0.3048\n"
        "filters = " + filters_repr + "\n"
        "return_params = " + rp_repr + "\n"
        "limit = " + str(lim) + "\n"
        "SPECIAL = {'type_name', 'level', 'volume', 'area', 'width', 'length'}\n"
        "bic = DB.BuiltInCategory." + ost + "\n"
        "elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
        ".WhereElementIsNotElementType().ToElements()\n"
        "results = []\n"
        "total_vol = 0.0\n"
        "total_area = 0.0\n"
        "for elem in elems:\n"
        "    if len(results) >= limit:\n"
        "        break\n"
        "    try:\n"
        "        te = doc.GetElement(elem.GetTypeId())\n"
        "        _p = te.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM) if te else None\n"
        "        type_name = _p.AsString() if (_p and _p.HasValue) else 'Unknown'\n"
        "        lvl_id = getattr(elem, 'LevelId', None)\n"
        "        level_name = ''\n"
        "        if lvl_id and lvl_id != DB.ElementId.InvalidElementId:\n"
        "            lvl = doc.GetElement(lvl_id)\n"
        "            try:\n"
        "                level_name = lvl.Name if lvl else ''\n"
        "            except Exception:\n"
        "                level_name = ''\n"
        "        vp = elem.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)\n"
        "        ap = elem.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)\n"
        "        wp = te.get_Parameter(DB.BuiltInParameter.WALL_ATTR_WIDTH_PARAM) if te else None\n"
        "        lp = elem.get_Parameter(DB.BuiltInParameter.CURVE_ELEM_LENGTH)\n"
        "        volume = (vp.AsDouble() * FT3_TO_M3) if (vp and vp.HasValue) else 0.0\n"
        "        area = (ap.AsDouble() * FT2_TO_M2) if (ap and ap.HasValue) else 0.0\n"
        "        width = (wp.AsDouble() * FT_TO_M) if (wp and wp.HasValue) else 0.0\n"
        "        length = (lp.AsDouble() * FT_TO_M) if (lp and lp.HasValue) else 0.0\n"
        "        def get_special(pname):\n"
        "            pn = pname.lower()\n"
        "            if pn == 'type_name': return type_name\n"
        "            if pn == 'level': return level_name\n"
        "            if pn == 'volume': return volume\n"
        "            if pn == 'area': return area\n"
        "            if pn == 'width': return width\n"
        "            if pn == 'length': return length\n"
        "            return None\n"
        "        def get_param_val(pname):\n"
        "            p = elem.LookupParameter(pname)\n"
        "            if not p:\n"
        "                p = te.LookupParameter(pname) if te else None\n"
        "            if not p or not p.HasValue: return None\n"
        "            st = p.StorageType.ToString()\n"
        "            if st == 'Double': return p.AsDouble()\n"
        "            if st == 'String': return p.AsString()\n"
        "            if st == 'Integer': return p.AsInteger()\n"
        "            return None\n"
        "        def check_filter(f):\n"
        "            pn = f.get('param', '')\n"
        "            op = f.get('op', 'eq')\n"
        "            v = f.get('value', None)\n"
        "            if pn.lower() in SPECIAL:\n"
        "                pv = get_special(pn)\n"
        "            else:\n"
        "                pv = get_param_val(pn)\n"
        "            if op == 'contains':\n"
        "                return isinstance(pv, str) and isinstance(v, str) and v.lower() in pv.lower()\n"
        "            if op == 'not_contains':\n"
        "                return not (isinstance(pv, str) and isinstance(v, str) and v.lower() in pv.lower())\n"
        "            if op == 'eq': return str(pv).lower() == str(v).lower()\n"
        "            if op == 'neq': return str(pv).lower() != str(v).lower()\n"
        "            if op == 'gt': return isinstance(pv, (int,float)) and pv > v\n"
        "            if op == 'lt': return isinstance(pv, (int,float)) and pv < v\n"
        "            if op == 'gte': return isinstance(pv, (int,float)) and pv >= v\n"
        "            if op == 'lte': return isinstance(pv, (int,float)) and pv <= v\n"
        "            if op == 'is_empty': return pv is None or pv == '' or pv == 0\n"
        "            if op == 'not_empty': return pv is not None and pv != '' and pv != 0\n"
        "            return False\n"
        "        passes = all(check_filter(f) for f in filters)\n"
        "        if passes:\n"
        "            row = {'id': elem.Id.IntegerValue, 'type_name': type_name,\n"
        "                   'level': level_name,\n"
        "                   'volume_m3': round(volume, 3),\n"
        "                   'area_m2': round(area, 3),\n"
        "                   'length_m': round(length, 3)}\n"
        "            if return_params:\n"
        "                for pn in return_params:\n"
        "                    if pn.lower() in SPECIAL:\n"
        "                        row[pn] = get_special(pn)\n"
        "                    else:\n"
        "                        row[pn] = get_param_val(pn)\n"
        "            results.append(row)\n"
        "            total_vol += volume\n"
        "            total_area += area\n"
        "    except: pass\n"
        "out = {'count': len(results),\n"
        "       'total_volume_m3': round(total_vol, 3),\n"
        "       'total_area_m2': round(total_area, 3),\n"
        "       'elements': results,\n"
        "       'colorized': False}\n"
        "print(json.dumps(out))\n"
    )
    return code


def _build_colorize_code(element_ids, color_rgb):
    ids_repr = repr(element_ids)
    r, g, b = color_rgb
    code = (
        "import json\n"
        "ids = " + ids_repr + "\n"
        "c = DB.Color(" + str(r) + ", " + str(g) + ", " + str(b) + ")\n"
        "ogs = DB.OverrideGraphicSettings()\n"
        "ogs.SetSurfaceForegroundPatternColor(c)\n"
        "ogs.SetProjectionLineColor(c)\n"
        "view = doc.ActiveView\n"
        "t = DB.Transaction(doc, 'BIM Search Colorize')\n"
        "colored = 0\n"
        "t.Start()\n"
        "try:\n"
        "    for eid in ids:\n"
        "        try:\n"
        "            view.SetElementOverrides(DB.ElementId(eid), ogs)\n"
        "            colored += 1\n"
        "        except: pass\n"
        "    t.Commit()\n"
        "except Exception as ex:\n"
        "    if t.HasStarted():\n"
        "        t.RollBack()\n"
        "    raise\n"
        "print(json.dumps({'colorized': colored}))\n"
    )
    return code


def register_bim_search_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM search tools."""

    @mcp_server.tool()
    async def bim_search(
        category: str,
        filters: list[dict],
        colorize: bool = False,
        color: str = "red",
        return_params: list[str] = None,
        limit: int = 500,
        ctx: Context = None,
    ) -> dict:
        """Search elements by parameters with multiple filter operators.

        category: Walls, Floors, Roofs, Columns, Doors, Windows, Pipes, Ducts, etc.
        filters: [{param, op, value}] — operators: contains/not_contains/eq/neq/gt/lt/gte/lte/is_empty/not_empty
        Special params: type_name, level, volume, area, width, length
        colorize: highlight matching elements in Revit active view
        color: red/blue/green/yellow/orange/purple
        return_params: extra parameters to include in each result row
        limit: max elements to return (default 500)
        """
        err = validate_filters(filters)
        if err:
            return {"error": "Validation error: " + err}

        code = _build_search_code(category, filters, return_params, limit)
        resp = await revit_post("/execute_code/", {"code": code}, ctx)
        if not (isinstance(resp, dict) and resp.get("status") == "success"):
            return {"error": str(resp)}

        raw = resp.get("output", "{}").strip()
        try:
            result = json.loads(raw)
        except Exception as e:
            return {"error": "Parse failed: {}".format(str(e)), "raw": raw[:500]}

        # Colorize if requested
        if colorize and result.get("elements"):
            ids = [el["id"] for el in result["elements"]]
            rgb = COLOR_MAP.get(color.lower(), (255, 0, 0))
            color_code = _build_colorize_code(ids, rgb)
            c_resp = await revit_post("/execute_code/", {"code": color_code}, ctx)
            if isinstance(c_resp, dict) and c_resp.get("status") == "success":
                result["colorized"] = True

        return result
