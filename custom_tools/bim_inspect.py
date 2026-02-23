# -*- coding: utf-8 -*-
"""BIM Inspect — full parameter dump for any element (like RevitLookup via MCP)."""
import json
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY, FT3_TO_M3, FT2_TO_M2, FT_TO_M
from ._validation import validate_element_id

CAT_MAP_INSPECT = {
    "Walls":                "OST_Walls",
    "Floors":               "OST_Floors",
    "Roofs":                "OST_Roofs",
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
}


def _build_inspect_by_id_code(element_id, max_params):
    eid = int(element_id)
    mp = int(max_params)
    code = (
        "import json\n"
        "FT3_TO_M3 = 0.028316846592\n"
        "FT2_TO_M2 = 0.09290304\n"
        "FT_TO_M = 0.3048\n"
        "elem_id = DB.ElementId(" + str(eid) + ")\n"
        "elem = doc.GetElement(elem_id)\n"
        "if elem is None:\n"
        "    print(json.dumps({'error': 'Element not found: " + str(eid) + "'}))\n"
        "else:\n"
        "    def read_params(element, limit):\n"
        "        params = {}\n"
        "        count = 0\n"
        "        for p in element.Parameters:\n"
        "            if count >= limit: break\n"
        "            try:\n"
        "                if not p: continue\n"
        "                pname = p.Definition.Name\n"
        "                val = None\n"
        "                if p.HasValue:\n"
        "                    st = p.StorageType.ToString()\n"
        "                    if st == 'Double': val = round(p.AsDouble(), 6)\n"
        "                    elif st == 'String': val = p.AsString()\n"
        "                    elif st == 'Integer': val = p.AsInteger()\n"
        "                    elif st == 'ElementId':\n"
        "                        eid2 = p.AsElementId()\n"
        "                        val = eid2.IntegerValue if eid2 else None\n"
        "                params[pname] = val\n"
        "                count += 1\n"
        "            except: pass\n"
        "        return params\n"
        "    te = doc.GetElement(elem.GetTypeId())\n"
        "    type_name = getattr(te, 'Name', None) or 'Unknown'\n"
        "    cat_name = elem.Category.Name if elem.Category else 'Unknown'\n"
        "    lvl_id = getattr(elem, 'LevelId', None)\n"
        "    level_name = ''\n"
        "    if lvl_id and lvl_id != DB.ElementId.InvalidElementId:\n"
        "        lvl = doc.GetElement(lvl_id)\n"
        "        level_name = lvl.Name if lvl else ''\n"
        "    loc = elem.Location\n"
        "    location = {}\n"
        "    if loc:\n"
        "        if hasattr(loc, 'Point'):\n"
        "            pt = loc.Point\n"
        "            location = {'x': round(pt.X * 0.3048, 3),\n"
        "                        'y': round(pt.Y * 0.3048, 3),\n"
        "                        'z': round(pt.Z * 0.3048, 3)}\n"
        "        elif hasattr(loc, 'Curve'):\n"
        "            c = loc.Curve\n"
        "            sp = c.GetEndPoint(0)\n"
        "            ep = c.GetEndPoint(1)\n"
        "            location = {'start': {'x': round(sp.X*0.3048,3), 'y': round(sp.Y*0.3048,3)},\n"
        "                        'end': {'x': round(ep.X*0.3048,3), 'y': round(ep.Y*0.3048,3)}}\n"
        "    inst_params = read_params(elem, " + str(mp) + ")\n"
        "    type_params = read_params(te, " + str(mp) + ") if te else {}\n"
        "    out = {'element_id': " + str(eid) + ",\n"
        "           'element_type': cat_name,\n"
        "           'type_name': type_name,\n"
        "           'type_id': te.Id.IntegerValue if te else 0,\n"
        "           'category': cat_name,\n"
        "           'level': level_name,\n"
        "           'location': location,\n"
        "           'instance_params': inst_params,\n"
        "           'type_params': type_params}\n"
        "    print(json.dumps(out))\n"
    )
    return code


def _build_inspect_by_type_name_code(category, type_name_str, max_params):
    ost = CAT_MAP_INSPECT.get(category, "OST_Walls")
    mp = int(max_params)
    tn_repr = repr(type_name_str)
    code = (
        "import json\n"
        "bic = DB.BuiltInCategory." + ost + "\n"
        "target_name = " + tn_repr + "\n"
        "elems = DB.FilteredElementCollector(doc).OfCategory(bic)"
        ".WhereElementIsNotElementType().ToElements()\n"
        "found_elem = None\n"
        "for elem in elems:\n"
        "    te = doc.GetElement(elem.GetTypeId())\n"
        "    tn = getattr(te, 'Name', '') or ''\n"
        "    if target_name.lower() in tn.lower():\n"
        "        found_elem = elem\n"
        "        break\n"
        "if found_elem is None:\n"
        "    print(json.dumps({'error': 'Type not found: ' + target_name}))\n"
        "else:\n"
        "    def read_params(element, limit):\n"
        "        params = {}\n"
        "        count = 0\n"
        "        for p in element.Parameters:\n"
        "            if count >= limit: break\n"
        "            try:\n"
        "                if not p: continue\n"
        "                pname = p.Definition.Name\n"
        "                val = None\n"
        "                if p.HasValue:\n"
        "                    st = p.StorageType.ToString()\n"
        "                    if st == 'Double': val = round(p.AsDouble(), 6)\n"
        "                    elif st == 'String': val = p.AsString()\n"
        "                    elif st == 'Integer': val = p.AsInteger()\n"
        "                params[pname] = val\n"
        "                count += 1\n"
        "            except: pass\n"
        "        return params\n"
        "    te = doc.GetElement(found_elem.GetTypeId())\n"
        "    type_nm = getattr(te, 'Name', None) or 'Unknown'\n"
        "    cat_nm = found_elem.Category.Name if found_elem.Category else 'Unknown'\n"
        "    lvl_id = getattr(found_elem, 'LevelId', None)\n"
        "    level_name = ''\n"
        "    if lvl_id and lvl_id != DB.ElementId.InvalidElementId:\n"
        "        lvl = doc.GetElement(lvl_id)\n"
        "        level_name = lvl.Name if lvl else ''\n"
        "    inst_params = read_params(found_elem, " + str(mp) + ")\n"
        "    type_params = read_params(te, " + str(mp) + ") if te else {}\n"
        "    out = {'element_id': found_elem.Id.IntegerValue,\n"
        "           'element_type': cat_nm, 'type_name': type_nm,\n"
        "           'type_id': te.Id.IntegerValue if te else 0,\n"
        "           'category': cat_nm, 'level': level_name,\n"
        "           'instance_params': inst_params, 'type_params': type_params}\n"
        "    print(json.dumps(out))\n"
    )
    return code


def register_bim_inspect_tools(mcp_server, revit_get, revit_post, revit_image):
    """Register BIM inspect tools."""

    @mcp_server.tool()
    async def bim_inspect(
        element_id: int = None,
        type_id: int = None,
        category: str = '',
        type_name: str = None,
        max_params: int = 200,
        ctx: Context = None,
    ) -> dict:
        """Full parameter dump for any element or type — like RevitLookup via MCP.

        element_id: inspect a specific instance by ID
        type_name + category: find first instance of that type in category
        max_params: max parameters to return per element (default 200)
        Returns: {element_id, type_name, category, level, location, instance_params, type_params}
        """
        if element_id is not None:
            err = validate_element_id(element_id)
            if err:
                return {"error": "Validation error: " + err}
            code = _build_inspect_by_id_code(element_id, max_params)
        elif type_name is not None:
            code = _build_inspect_by_type_name_code(category, type_name, max_params)
        elif type_id is not None:
            # Inspect by type ID — find first instance
            if category and category in CAT_MAP_INSPECT:
                _cat_filter = ".OfCategory(DB.BuiltInCategory.{})".format(CAT_MAP_INSPECT[category])
            else:
                _cat_filter = ""
            code = (
                "import json\n"
                "target_tid = DB.ElementId(" + str(int(type_id)) + ")\n"
                "elems = DB.FilteredElementCollector(doc)" + _cat_filter + ".WhereElementIsNotElementType().ToElements()\n"
                "found = None\n"
                "for e in elems:\n"
                "    if e.GetTypeId() == target_tid:\n"
                "        found = e\n"
                "        break\n"
                "if found is None:\n"
                "    print(json.dumps({'error': 'No instance found for type_id: " + str(int(type_id)) + "'}))\n"
                "else:\n"
                "    def read_params(element, limit):\n"
                "        params = {}\n"
                "        count = 0\n"
                "        for p in element.Parameters:\n"
                "            if count >= limit: break\n"
                "            try:\n"
                "                if not p: continue\n"
                "                pname = p.Definition.Name\n"
                "                val = None\n"
                "                if p.HasValue:\n"
                "                    st = p.StorageType.ToString()\n"
                "                    if st == 'Double': val = round(p.AsDouble(), 6)\n"
                "                    elif st == 'String': val = p.AsString()\n"
                "                    elif st == 'Integer': val = p.AsInteger()\n"
                "                params[pname] = val\n"
                "                count += 1\n"
                "            except: pass\n"
                "        return params\n"
                "    te = doc.GetElement(found.GetTypeId())\n"
                "    out = {'element_id': found.Id.IntegerValue,\n"
                "           'type_name': getattr(te, 'Name', 'Unknown') or 'Unknown',\n"
                "           'type_id': te.Id.IntegerValue if te else 0,\n"
                "           'category': found.Category.Name if found.Category else 'Unknown',\n"
                "           'instance_params': read_params(found, 200),\n"
                "           'type_params': read_params(te, 200) if te else {}}\n"
                "    print(json.dumps(out))\n"
            )
        else:
            return {"error": "Provide element_id, type_id, or (type_name + category)"}

        resp = await revit_post("/execute_code/", {"code": code}, ctx)
        if isinstance(resp, dict) and resp.get("status") == "success":
            raw = resp.get("output", "{}").strip()
            try:
                return json.loads(raw)
            except Exception as e:
                return {"error": "Parse failed: {}".format(str(e)), "raw": raw[:500]}
        return {"error": str(resp)}
