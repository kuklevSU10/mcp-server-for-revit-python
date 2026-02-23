# -*- coding: UTF-8 -*-
"""Revit MCP Extension Startup — Debug version"""

import sys
import os.path as op
import traceback

# Add extension directory to sys.path
ext_dir = op.dirname(__file__)
if ext_dir not in sys.path:
    sys.path.append(ext_dir)

print("revit-mcp: ext_dir = {}".format(ext_dir))

try:
    from pyrevit import routes
    print("revit-mcp: pyrevit.routes imported OK")
except Exception as e:
    print("revit-mcp: FAILED to import pyrevit.routes: {}".format(e))
    traceback.print_exc()

try:
    api = routes.API("revit_mcp")
    print("revit-mcp: API 'revit_mcp' created OK")
except Exception as e:
    print("revit-mcp: FAILED to create API: {}".format(e))
    traceback.print_exc()

# Try importing each module one by one
modules = [
    ("revit_mcp.status", "register_status_routes"),
    ("revit_mcp.model_info", "register_model_info_routes"),
    ("revit_mcp.views", "register_views_routes"),
    ("revit_mcp.placement", "register_placement_routes"),
    ("revit_mcp.colors", "register_color_routes"),
    ("revit_mcp.code_execution", "register_code_execution_routes"),
]

for mod_name, func_name in modules:
    try:
        # Force fresh import by clearing cached module (fixes state after failed reload)
        import sys as _sys
        for _cached in list(_sys.modules.keys()):
            if _cached == mod_name or _cached.startswith(mod_name + "."):
                del _sys.modules[_cached]
        # Also clear parent package if needed
        parent = mod_name.rsplit(".", 1)[0]
        if parent != mod_name and parent in _sys.modules:
            del _sys.modules[parent]

        mod = __import__(mod_name, fromlist=[func_name])
        func = getattr(mod, func_name)
        func(api)
        print("revit-mcp: {} -> OK".format(mod_name))
    except Exception as e:
        print("revit-mcp: {} -> FAILED: {}".format(mod_name, e))
        traceback.print_exc()

print("revit-mcp: startup complete")
