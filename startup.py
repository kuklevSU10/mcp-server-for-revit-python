# -*- coding: UTF-8 -*-
"""Revit MCP Extension Startup — Debug version"""

import sys
import os
import os.path as op
import traceback

# Лог в файл — читаем снаружи
_LOG = r"C:\Users\kuklev.d.s\AppData\Temp\revit_mcp_startup.log"
try:
    os.makedirs(os.path.dirname(_LOG), exist_ok=True)
except Exception:
    _LOG = r"C:\Temp\revit_mcp_startup.log"
    try:
        os.makedirs(r"C:\Temp", exist_ok=True)
    except Exception:
        _LOG = None

def _log(msg):
    print(msg)
    if _LOG:
        try:
            with open(_LOG, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass

# Очистить лог при старте
if _LOG:
    try:
        open(_LOG, "w").close()
    except Exception:
        pass

# Add extension directory to sys.path
ext_dir = op.dirname(__file__)
if ext_dir not in sys.path:
    sys.path.append(ext_dir)

_log("revit-mcp: ext_dir = {}".format(ext_dir))

try:
    from pyrevit import routes
    _log("revit-mcp: pyrevit.routes imported OK")
except Exception as e:
    _log("revit-mcp: FAILED to import pyrevit.routes: {}".format(e))
    traceback.print_exc()

try:
    api = routes.API("revit_mcp")
    _log("revit-mcp: API 'revit_mcp' created OK")
except Exception as e:
    _log("revit-mcp: FAILED to create API: {}".format(e))
    traceback.print_exc()

# Try importing each module one by one
modules = [
    ("revit_mcp.status", "register_status_routes"),
    ("revit_mcp.model_info", "register_model_info_routes"),
    ("revit_mcp.views", "register_views_routes"),
    ("revit_mcp.placement", "register_placement_routes"),
    ("revit_mcp.colors", "register_color_routes"),
    ("revit_mcp.code_execution", "register_code_execution_routes"),
    ("revit_mcp.execute_v2_route", "register_execute_v2_routes"),
]

# Clear cached submodules once before importing (so fresh code is picked up)
import sys as _sys
for _key in list(_sys.modules.keys()):
    if _key == "revit_mcp" or _key.startswith("revit_mcp."):
        del _sys.modules[_key]

for mod_name, func_name in modules:
    try:
        mod = __import__(mod_name, fromlist=[func_name])
        func = getattr(mod, func_name)
        func(api)
        _log("revit-mcp: {} -> OK".format(mod_name))
    except Exception as e:
        _log("revit-mcp: {} -> FAILED: {}".format(mod_name, e))
        traceback.print_exc()

_log("revit-mcp: startup complete")

# Verify routes were registered
try:
    from pyrevit.routes.server import router as _router
    _routes = _router.get_routes("revit_mcp")
    _log("revit-mcp: {} routes registered in revit_mcp".format(len(_routes)))
    for _r in _routes:
        print("  -> {} {}".format(_r.method, _r.pattern))
except Exception as _e:
    _log("revit-mcp: route verify error: {}".format(_e))

