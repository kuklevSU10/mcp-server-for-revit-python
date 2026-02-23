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
AUDIT_DUPLICATE_CATEGORIES = ['Walls', 'Floors', 'Columns', 'Beams', 'Foundations']
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
    'Beams': {
        'ost': 'OST_StructuralFraming',
        'has_volume': True,
        'has_area': False,
        'has_length': True,
    },
    'Foundations': {
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
    'Railings': {
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
}

# ---------------------------------------------------------------------------
# Category map: name -> (OST_Name, has_volume, has_area, has_length)
# Used by bim_catalog, bim_summary, vor_vs_bim, bim_query
# ---------------------------------------------------------------------------
ALL_CATEGORIES = {
    # Structural
    "Walls":               ("OST_Walls",              True,  True,  False),
    "Floors":              ("OST_Floors",             True,  True,  False),
    "Roofs":               ("OST_Roofs",              True,  True,  False),
    "Ceilings":            ("OST_Ceilings",           False, True,  False),
    "Columns":             ("OST_StructuralColumns",  True,  False, False),
    "StructuralFraming":   ("OST_StructuralFraming",  True,  False, True),
    "StructuralFoundation":("OST_StructuralFoundation",True, True,  False),
    "Ramps":               ("OST_Ramps",              False, True,  False),
    "Stairs":              ("OST_Stairs",             False, False, False),
    "StairsRailing":       ("OST_StairsRailing",      False, False, True),
    # Architectural
    "Doors":               ("OST_Doors",              False, False, False),
    "Windows":             ("OST_Windows",            False, False, False),
    "Furniture":           ("OST_Furniture",          False, False, False),
    "FurnitureSystems":    ("OST_FurnitureSystems",   False, False, False),
    "CurtainWallPanels":   ("OST_CurtainWallPanels",  False, True,  False),
    "GenericModel":        ("OST_GenericModel",       False, False, False),
    "Casework":            ("OST_Casework",           False, False, False),
    # MEP
    "Ducts":               ("OST_DuctCurves",         False, False, True),
    "Pipes":               ("OST_PipeCurves",         False, False, True),
    "MechanicalEquipment": ("OST_MechanicalEquipment",False, False, False),
    "PlumbingFixtures":    ("OST_PlumbingFixtures",   False, False, False),
    "FlexDucts":           ("OST_FlexDuctCurves",     False, False, True),
    "FlexPipes":           ("OST_FlexPipeCurves",     False, False, True),
    "DuctAccessory":       ("OST_DuctAccessory",      False, False, False),
    "PipeAccessory":       ("OST_PipeAccessory",      False, False, False),
    # Electrical
    "ElectricalEquipment": ("OST_ElectricalEquipment",False, False, False),
    "ElectricalFixtures":  ("OST_ElectricalFixtures", False, False, False),
    "LightingFixtures":    ("OST_LightingFixtures",   False, False, False),
    "CableTray":           ("OST_CableTray",          False, False, True),
    "Conduit":             ("OST_Conduit",            False, False, True),
}

# Batch groups for scanning (5-6 categories per batch to avoid Revit timeout)
CAT_BATCHES = [
    ["Walls", "Floors", "Roofs", "Ceilings", "Columns"],
    ["StructuralFraming", "StructuralFoundation", "Ramps", "Stairs", "StairsRailing"],
    ["Doors", "Windows", "Furniture", "FurnitureSystems", "CurtainWallPanels"],
    ["GenericModel", "Casework", "Ducts", "Pipes", "MechanicalEquipment"],
    ["PlumbingFixtures", "FlexDucts", "FlexPipes", "DuctAccessory", "PipeAccessory"],
    ["ElectricalEquipment", "ElectricalFixtures", "LightingFixtures", "CableTray", "Conduit"],
]
