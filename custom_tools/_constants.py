# -*- coding: utf-8 -*-
"""
_constants.py — shared constants for all BIM custom tools.
Single source of truth for unit conversions, category registry, and limits.
"""

# ============================================================
# Unit conversion coefficients (exact values)
# ============================================================
FT3_TO_M3 = 0.028316846592    # cubic feet → cubic metres
FT2_TO_M2 = 0.09290304        # square feet → square metres
FT_TO_M   = 0.3048            # feet → metres

# ============================================================
# Scan / output limits
# ============================================================
MAX_BATCH_SIZE        = 5
DEFAULT_SEARCH_LIMIT  = 500
DEFAULT_MAX_PARAMS    = 200

# Audit duplicate checks
AUDIT_DUPLICATE_CATEGORIES = ['Walls', 'Floors', 'Columns', 'StructuralFraming', 'StructuralFoundation']
AUDIT_MAX_DUPLICATES       = 200

# ============================================================
# CATEGORY_REGISTRY
# key  = human-readable name
# value = {
#   'ost':        OST_* enum name (string, no "DB.BuiltInCategory." prefix),
#   'has_volume': bool,
#   'has_area':   bool,
#   'has_length': bool,
# }
# ============================================================
CATEGORY_REGISTRY = {
    # --- Structural ---
    'Walls': {
        'ost': 'OST_Walls',
        'has_volume': True,
        'has_area': True,
        'has_length': False,
    },
    'Floors': {
        'ost': 'OST_Floors',
        'has_volume': True,
        'has_area': True,
        'has_length': False,
    },
    'Roofs': {
        'ost': 'OST_Roofs',
        'has_volume': True,
        'has_area': True,
        'has_length': False,
    },
    'Columns': {
        'ost': 'OST_StructuralColumns',
        'has_volume': True,
        'has_area': False,
        'has_length': False,
    },
    'StructuralFraming': {
        'ost': 'OST_StructuralFraming',
        'has_volume': True,
        'has_area': False,
        'has_length': True,
    },
    'StructuralFoundation': {
        'ost': 'OST_StructuralFoundation',
        'has_volume': True,
        'has_area': True,
        'has_length': False,
    },
    'Ramps': {
        'ost': 'OST_Ramps',
        'has_volume': False,
        'has_area': True,
        'has_length': False,
    },
    'Stairs': {
        'ost': 'OST_Stairs',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'StairsRailing': {
        'ost': 'OST_StairsRailing',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    # --- Architectural ---
    'Ceilings': {
        'ost': 'OST_Ceilings',
        'has_volume': False,
        'has_area': True,
        'has_length': False,
    },
    'Doors': {
        'ost': 'OST_Doors',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'Windows': {
        'ost': 'OST_Windows',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'Furniture': {
        'ost': 'OST_Furniture',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'FurnitureSystems': {
        'ost': 'OST_FurnitureSystems',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'Casework': {
        'ost': 'OST_Casework',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'CurtainWallPanels': {
        'ost': 'OST_CurtainWallPanels',
        'has_volume': False,
        'has_area': True,
        'has_length': False,
    },
    'CurtainWallMullions': {
        'ost': 'OST_CurtainWallMullions',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'GenericModel': {
        'ost': 'OST_GenericModel',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'SpecialtyEquipment': {
        'ost': 'OST_SpecialtyEquipment',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    # --- Spaces ---
    'Rooms': {
        'ost': 'OST_Rooms',
        'has_volume': False,
        'has_area': True,
        'has_length': False,
    },
    'Spaces': {
        'ost': 'OST_MEPSpaces',
        'has_volume': False,
        'has_area': True,
        'has_length': False,
    },
    # --- MEP ---
    'Ducts': {
        'ost': 'OST_DuctCurves',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'Pipes': {
        'ost': 'OST_PipeCurves',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'CableTray': {
        'ost': 'OST_CableTray',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'Conduit': {
        'ost': 'OST_Conduit',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'MechanicalEquipment': {
        'ost': 'OST_MechanicalEquipment',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'ElectricalEquipment': {
        'ost': 'OST_ElectricalEquipment',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'ElectricalFixtures': {
        'ost': 'OST_ElectricalFixtures',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'LightingFixtures': {
        'ost': 'OST_LightingFixtures',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'PlumbingFixtures': {
        'ost': 'OST_PlumbingFixtures',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'FlexDucts': {
        'ost': 'OST_FlexDuctCurves',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'FlexPipes': {
        'ost': 'OST_FlexPipeCurves',
        'has_volume': False,
        'has_area': False,
        'has_length': True,
    },
    'DuctAccessory': {
        'ost': 'OST_DuctAccessory',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
    'PipeAccessory': {
        'ost': 'OST_PipeAccessory',
        'has_volume': False,
        'has_area': False,
        'has_length': False,
    },
}

# ---------------------------------------------------------------------------
# ALL_CATEGORIES — auto-generated from CATEGORY_REGISTRY
# Format: name -> (OST_Name, has_volume, has_area, has_length)
# Used by bim_catalog, bim_summary, vor_vs_bim, bim_query, _scan_engine
# ---------------------------------------------------------------------------
ALL_CATEGORIES = {
    k: (v['ost'], v['has_volume'], v['has_area'], v['has_length'])
    for k, v in CATEGORY_REGISTRY.items()
}

# Simple name -> OST map for tools that only need the OST string
CAT_OST_MAP = {k: v['ost'] for k, v in CATEGORY_REGISTRY.items()}

# ---------------------------------------------------------------------------
# ironpython_cat_map — generate IronPython CAT_MAP snippet for code strings
# Used by bim_report, bim_volumes, bim_to_vor, bim_vor_to_sheets, bim_audit
# ---------------------------------------------------------------------------
def ironpython_cat_map(categories):
    """Generate IronPython code for a CAT_MAP = {name: DB.BuiltInCategory.OST_*} dict.

    Args:
        categories: list of category name strings (keys of CATEGORY_REGISTRY)

    Returns:
        str — multi-line IronPython code snippet ready for embedding.
    """
    lines = ["CAT_MAP = {"]
    for name in categories:
        info = CATEGORY_REGISTRY.get(name)
        if info:
            lines.append("    '{}': DB.BuiltInCategory.{},".format(name, info['ost']))
    lines.append("}\n")
    return "\n".join(lines)


# Batch groups for scanning (5-6 categories per batch to avoid Revit timeout)
CAT_BATCHES = [
    ["Walls", "Floors", "Roofs", "Ceilings", "Columns"],
    ["StructuralFraming", "StructuralFoundation", "Ramps", "Stairs", "StairsRailing"],
    ["Doors", "Windows", "Furniture", "FurnitureSystems", "CurtainWallPanels"],
    ["GenericModel", "Casework", "Ducts", "Pipes", "MechanicalEquipment"],
    ["PlumbingFixtures", "FlexDucts", "FlexPipes", "DuctAccessory", "PipeAccessory"],
    ["ElectricalEquipment", "ElectricalFixtures", "LightingFixtures", "CableTray", "Conduit"],
]
