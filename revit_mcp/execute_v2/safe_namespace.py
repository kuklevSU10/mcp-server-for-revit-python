"""
Safe Namespace — whitelist-based namespace for exec() in Revit.

Provides a restricted __builtins__ dict and injects Revit objects (doc, uidoc, DB, revit).
Runs on Python 3 side to BUILD the namespace dict; the dict is then used inside Revit exec().
"""

import builtins
from typing import Any, Dict, List


# Builtins that are ALLOWED in the sandbox
SAFE_BUILTINS_NAMES = [
    "print",  # will be overridden with captured version
    "len", "range", "enumerate", "zip",
    "list", "dict", "tuple", "set", "frozenset",
    "str", "int", "float", "bool", "bytes", "bytearray",
    "abs", "min", "max", "sum",
    "sorted", "reversed",
    "any", "all",
    "isinstance", "issubclass",
    "hasattr", "getattr",
    "type", "repr", "round",
    "map", "filter",
    "chr", "ord",
    "hex", "oct", "bin",
    "callable",
    "iter", "next",
    "slice",
    "staticmethod", "classmethod", "property",
    "super", "object",
    "True", "False", "None",
    "ValueError", "TypeError", "KeyError", "IndexError",
    "AttributeError", "RuntimeError", "StopIteration",
    "Exception", "BaseException",
    "NotImplementedError", "ZeroDivisionError",
    "OverflowError", "ArithmeticError",
    "IOError", "OSError",
]

# Builtins explicitly BLOCKED
BLOCKED_BUILTINS = {
    "__import__", "open", "file", "execfile", "reload",
    "input", "raw_input", "compile", "__build_class__",
    "exec", "eval",
}


def _build_safe_builtins() -> Dict[str, Any]:
    """Build a restricted __builtins__ dict from the whitelist."""
    safe = {}
    for name in SAFE_BUILTINS_NAMES:
        val = getattr(builtins, name, None)
        if val is not None:
            safe[name] = val
    return safe


def _make_captured_print(captured_output: List[str]):
    """Create a print function that appends to captured_output list."""
    def safe_print(*args, **kwargs):
        sep = kwargs.get("sep", " ")
        end = kwargs.get("end", "\n")
        output = sep.join(str(a) for a in args) + end
        captured_output.append(output)
    return safe_print


def build_safe_namespace(
    doc: Any,
    uidoc: Any,
    DB: Any,
    revit: Any,
    captured_output: List[str],
) -> Dict[str, Any]:
    """
    Build a safe execution namespace for IronPython code.

    Args:
        doc: Revit Document object
        uidoc: Revit UIDocument object
        DB: Autodesk.Revit.DB module
        revit: pyRevit revit module
        captured_output: list to capture print() output

    Returns:
        Dict namespace ready for exec()
    """
    safe_builtins = _build_safe_builtins()
    safe_builtins["print"] = _make_captured_print(captured_output)

    # ElementId helper: Revit 2024+ uses .Value (Int64), older uses .IntegerValue
    def _eid_value(eid):
        return getattr(eid, "Value", None) if hasattr(eid, "Value") else eid.IntegerValue

    # .NET Generic List helper (needed for Revit API calls like IsolateElementsTemporary)
    try:
        from System.Collections.Generic import List as _NetList
        _net_list = _NetList
    except Exception:
        _net_list = None

    namespace = {
        "__builtins__": safe_builtins,
        # Revit objects
        "doc": doc,
        "uidoc": uidoc,
        "DB": DB,
        "revit": revit,
        # Helpers
        "eid_value": _eid_value,      # Revit 2023/2024/2025 compatible ElementId value
        "NetList": _net_list,          # System.Collections.Generic.List
        # Result placeholder
        "__result__": None,
    }

    # Expose captured output so _collect_output() can find it
    namespace["__captured_output__"] = captured_output

    # Pre-inject commonly used stdlib modules (import is blocked by sandbox)
    import json as _json
    import math as _math
    import re as _re
    import collections as _collections

    namespace["json"] = _json
    namespace["math"] = _math
    namespace["re"] = _re
    namespace["collections"] = _collections

    return namespace
