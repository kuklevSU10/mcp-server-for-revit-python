"""
Context Builder — collects Revit model context for LLM prompts.

Two modes:
1. IronPython code generation (build_context_code) — returns code string to execute in Revit
2. Python 3 wrapper with TTL cache (ContextBuilder class)

The IronPython code is executed inside Revit and sets __result__ with context dict.
"""

import time
from typing import Any, Dict, Optional

from revit_mcp.execute_v2.context_cache import ContextCache


# IronPython 2.7 compatible code that runs inside Revit
# NO f-strings, NO type hints, NO walrus operator
CONTEXT_COLLECTION_CODE = '''
# Context collection code — runs inside Revit (IronPython 2.7)
# Collects model metadata for LLM prompt context

context = {}

# Project name
try:
    proj_info = doc.ProjectInformation
    context["project_name"] = proj_info.Name or "Unknown"
except Exception:
    context["project_name"] = "Unknown"

# Revit version
try:
    context["revit_version"] = str(doc.Application.VersionNumber)
except Exception:
    context["revit_version"] = "Unknown"

# Active view
try:
    av = doc.ActiveView
    view_info = {"name": av.Name, "type": str(av.ViewType)}
    try:
        if hasattr(av, "GenLevel") and av.GenLevel:
            view_info["level"] = av.GenLevel.Name
        else:
            view_info["level"] = None
    except Exception:
        view_info["level"] = None
    context["active_view"] = view_info
except Exception:
    context["active_view"] = {"name": "Unknown", "type": "Unknown", "level": None}

# Levels
try:
    level_collector = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
    levels = []
    for lvl in level_collector:
        levels.append({
            "name": lvl.Name,
            "elevation": round(lvl.Elevation * 0.3048, 2)
        })
    levels.sort(key=lambda x: x["elevation"])
    context["levels"] = levels
except Exception:
    context["levels"] = []

# Categories summary (top 15 by element count)
try:
    category_counts = {}
    all_categories = [
        (DB.BuiltInCategory.OST_Walls, "Walls"),
        (DB.BuiltInCategory.OST_Floors, "Floors"),
        (DB.BuiltInCategory.OST_Doors, "Doors"),
        (DB.BuiltInCategory.OST_Windows, "Windows"),
        (DB.BuiltInCategory.OST_Roofs, "Roofs"),
        (DB.BuiltInCategory.OST_Columns, "Columns"),
        (DB.BuiltInCategory.OST_StructuralColumns, "Structural Columns"),
        (DB.BuiltInCategory.OST_StructuralFraming, "Structural Framing"),
        (DB.BuiltInCategory.OST_Rooms, "Rooms"),
        (DB.BuiltInCategory.OST_Ceilings, "Ceilings"),
        (DB.BuiltInCategory.OST_Stairs, "Stairs"),
        (DB.BuiltInCategory.OST_Railings, "Railings"),
        (DB.BuiltInCategory.OST_Furniture, "Furniture"),
        (DB.BuiltInCategory.OST_MechanicalEquipment, "Mechanical Equipment"),
        (DB.BuiltInCategory.OST_Pipes, "Pipes"),
        (DB.BuiltInCategory.OST_PipeFitting, "Pipe Fittings"),
        (DB.BuiltInCategory.OST_DuctCurves, "Ducts"),
        (DB.BuiltInCategory.OST_CableTray, "Cable Trays"),
        (DB.BuiltInCategory.OST_ElectricalFixtures, "Electrical Fixtures"),
        (DB.BuiltInCategory.OST_Parking, "Parking"),
    ]
    for cat_enum, cat_name in all_categories:
        try:
            cnt = DB.FilteredElementCollector(doc).OfCategory(cat_enum).WhereElementIsNotElementType().GetElementCount()
            if cnt > 0:
                category_counts[cat_name] = cnt
        except Exception:
            pass
    # Sort by count desc and take top 15
    sorted_cats = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)[:15]
    context["categories_summary"] = dict(sorted_cats)
except Exception:
    context["categories_summary"] = {}

# Selected elements (max 10)
try:
    sel_ids = uidoc.Selection.GetElementIds()
    selected = []
    count = 0
    for eid in sel_ids:
        if count >= 10:
            break
        el = doc.GetElement(eid)
        if el is not None:
            el_info = {"id": eid.IntegerValue}
            try:
                el_info["category"] = el.Category.Name if el.Category else "Unknown"
            except Exception:
                el_info["category"] = "Unknown"
            try:
                el_info["name"] = el.Name
            except Exception:
                el_info["name"] = "Unknown"
            selected.append(el_info)
        count += 1
    context["selected_elements"] = selected
except Exception:
    context["selected_elements"] = []

# Phases
try:
    phases = []
    phase_collector = doc.Phases
    for i in range(phase_collector.Size):
        phases.append(phase_collector.get_Item(i).Name)
    context["phases"] = phases
except Exception:
    context["phases"] = []

# Family names for top 5 categories
try:
    family_names = {}
    top5_cats = [
        (DB.BuiltInCategory.OST_Walls, "Walls"),
        (DB.BuiltInCategory.OST_Doors, "Doors"),
        (DB.BuiltInCategory.OST_Windows, "Windows"),
        (DB.BuiltInCategory.OST_Rooms, "Rooms"),
        (DB.BuiltInCategory.OST_Floors, "Floors"),
    ]
    for cat_enum, cat_name in top5_cats:
        try:
            types = DB.FilteredElementCollector(doc).OfCategory(cat_enum).WhereElementIsElementType().ToElements()
            names = []
            seen = set()
            for t in types:
                try:
                    n = t.Name
                    if n and n not in seen:
                        seen.add(n)
                        names.append(n)
                        if len(names) >= 10:
                            break
                except Exception:
                    pass
            if names:
                family_names[cat_name] = names
        except Exception:
            pass
    context["family_names"] = family_names
except Exception:
    context["family_names"] = {}

# Workset info
try:
    if doc.IsWorkshared:
        worksets = []
        ws_table = doc.GetWorksetTable()
        ws_collector = DB.FilteredWorksetCollector(doc).OfKind(DB.WorksetKind.UserWorkset)
        for ws in ws_collector:
            worksets.append({"name": ws.Name, "id": ws.Id.IntegerValue, "visible": ws.IsOpen})
        context["worksets"] = worksets
        context["is_workshared"] = True
    else:
        context["worksets"] = []
        context["is_workshared"] = False
except Exception:
    context["worksets"] = []
    context["is_workshared"] = False

# Views (first 10 floor plans + sections)
try:
    views_list = []
    view_collector = DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
    plan_count = 0
    section_count = 0
    for v in view_collector:
        try:
            if v.IsTemplate:
                continue
            vt = v.ViewType
            if vt == DB.ViewType.FloorPlan and plan_count < 10:
                views_list.append({"name": v.Name, "type": "FloorPlan"})
                plan_count += 1
            elif vt == DB.ViewType.Section and section_count < 10:
                views_list.append({"name": v.Name, "type": "Section"})
                section_count += 1
        except Exception:
            pass
    context["views"] = views_list
except Exception:
    context["views"] = []

# Project parameters
try:
    proj_info = doc.ProjectInformation
    proj_params = {}
    try:
        proj_params["number"] = proj_info.Number or ""
    except Exception:
        proj_params["number"] = ""
    try:
        proj_params["address"] = proj_info.Address or ""
    except Exception:
        proj_params["address"] = ""
    try:
        proj_params["name"] = proj_info.BuildingName or ""
    except Exception:
        proj_params["name"] = ""
    try:
        proj_params["client_name"] = proj_info.ClientName or ""
    except Exception:
        proj_params["client_name"] = ""
    context["project_info"] = proj_params
except Exception:
    context["project_info"] = {}

__result__ = context
'''


MINIMAL_CONTEXT_CODE = '''
# Minimal context — fast version for READ requests
context = {}
try:
    proj_info = doc.ProjectInformation
    context["project_name"] = proj_info.Name or "Unknown"
except Exception:
    context["project_name"] = "Unknown"
try:
    av = doc.ActiveView
    context["active_view"] = {"name": av.Name, "type": str(av.ViewType)}
except Exception:
    context["active_view"] = {"name": "Unknown", "type": "Unknown"}
try:
    lvls = DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements()
    context["levels"] = [{"name": l.Name, "elevation": round(l.Elevation * 0.3048, 2)} for l in lvls]
except Exception:
    context["levels"] = []
try:
    cats = {}
    for cat_enum, cat_name in [
        (DB.BuiltInCategory.OST_Walls, "Walls"),
        (DB.BuiltInCategory.OST_Doors, "Doors"),
        (DB.BuiltInCategory.OST_Windows, "Windows"),
        (DB.BuiltInCategory.OST_Rooms, "Rooms"),
        (DB.BuiltInCategory.OST_Floors, "Floors"),
    ]:
        try:
            cnt = DB.FilteredElementCollector(doc).OfCategory(cat_enum).WhereElementIsNotElementType().GetElementCount()
            if cnt > 0:
                cats[cat_name] = cnt
        except Exception:
            pass
    context["categories_summary"] = cats
except Exception:
    context["categories_summary"] = {}
__result__ = context
'''


class ContextBuilder:
    """
    Builds Revit model context for LLM prompts.
    
    Python 3 wrapper with TTL cache (5 minutes).
    The actual context collection happens via IronPython code executed in Revit.
    """

    CACHE_TTL_SECONDS = 300  # 5 minutes

    def __init__(self):
        self._cache = None  # type: Optional[Dict]
        self._cache_time = 0.0  # type: float

    def get_context_code(self):
        """
        Return the IronPython code string that collects context.
        This code is meant to be executed inside Revit via execute_code.
        Sets __result__ = context dict.
        """
        return CONTEXT_COLLECTION_CODE

    def get_minimal_context_code(self):
        """Return minimal IronPython context code (fast, for READ requests)."""
        return MINIMAL_CONTEXT_CODE

    def build(self, doc, uidoc):
        """
        Build context dict from Revit objects.
        
        NOTE: This method is for direct execution when doc/uidoc are available
        in the same Python process (e.g., testing with mocks).
        In production, use get_context_code() and execute in Revit.
        
        Args:
            doc: Revit Document
            uidoc: Revit UIDocument
            
        Returns:
            Context dict with model metadata.
        """
        # Check cache
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self.CACHE_TTL_SECONDS:
            return self._cache

        context = self._collect_context(doc, uidoc)
        self._cache = context
        self._cache_time = now
        return context

    def invalidate_cache(self):
        """Force cache invalidation."""
        self._cache = None
        self._cache_time = 0.0

    def build_from_result(self, result_dict):
        """
        Store a context dict obtained from executing get_context_code() in Revit.
        Caches the result.
        
        Args:
            result_dict: The __result__ dict from running CONTEXT_COLLECTION_CODE in Revit.
            
        Returns:
            The same dict (for chaining).
        """
        self._cache = result_dict
        self._cache_time = time.time()
        return result_dict

    def _collect_context(self, doc, uidoc):
        """
        Collect context directly from doc/uidoc objects.
        Works when running in the same process as Revit (or with mocks).
        """
        context = {}

        # Project name
        try:
            context["project_name"] = doc.ProjectInformation.Name or "Unknown"
        except Exception:
            context["project_name"] = "Unknown"

        # Revit version
        try:
            context["revit_version"] = str(doc.Application.VersionNumber)
        except Exception:
            context["revit_version"] = "Unknown"

        # Active view
        try:
            av = doc.ActiveView
            view_info = {"name": av.Name, "type": str(av.ViewType)}
            try:
                if hasattr(av, "GenLevel") and av.GenLevel:
                    view_info["level"] = av.GenLevel.Name
                else:
                    view_info["level"] = None
            except Exception:
                view_info["level"] = None
            context["active_view"] = view_info
        except Exception:
            context["active_view"] = {"name": "Unknown", "type": "Unknown", "level": None}

        # Levels — simplified for mock compatibility
        context["levels"] = []
        
        # Categories summary
        context["categories_summary"] = {}

        # Selected elements
        context["selected_elements"] = []

        # Phases
        context["phases"] = []

        return context
