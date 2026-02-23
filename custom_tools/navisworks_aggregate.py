# -*- coding: utf-8 -*-
"""
MCP tools: nw_aggregate_models, nw_aggregate_via_plugin
Build federated NWD models from NWC/NWF files.
"""

import asyncio
import os
import subprocess
from typing import List, Optional
from ._navisworks_client import _nw_call, _nw_is_available

# Path to NavisworksBatch.exe (compiled from NavisworksBatch project)
# Adjust if compiled to a different location
_BATCH_EXE_PATHS = [
    r"C:\Users\kuklev.d.s\clawd\projects\revit-openclaw\navisworks-plugin\NavisworksBatch\bin\Release\NavisworksBatch.exe",
    r"C:\Users\kuklev.d.s\clawd\projects\revit-openclaw\navisworks-plugin\NavisworksBatch\bin\Debug\NavisworksBatch.exe",
]


def _find_batch_exe():
    for path in _BATCH_EXE_PATHS:
        if os.path.exists(path):
            return path
    return None


async def nw_aggregate_models(nwc_files: List[str], output_path: str) -> dict:
    """
    Собрать федеративную NWD модель из списка NWC/NWF файлов.

    Работает двумя способами (автовыбор):
    1. Через запущенный Navisworks + плагин (POST /aggregate) — предпочтительно
    2. Headless через NavisworksBatch.exe (без GUI) — если плагин недоступен

    Args:
        nwc_files:   Список путей к NWC/NWF файлам.
                     Например: ["C:/models/AR.nwc", "C:/models/KR.nwc"]
        output_path: Путь для сохранения федеративной NWD модели.
                     Например: "C:/models/Federated.nwd"

    Returns:
        {
            "success": true,
            "method": "plugin" | "headless",
            "appended_count": 3,
            "appended": ["AR.nwc", "KR.nwc", "OV.nwc"],
            "saved_to": "C:/models/Federated.nwd"
        }
    """
    if not nwc_files:
        return {"error": "nwc_files list is empty"}
    if not output_path:
        return {"error": "output_path is required"}

    # Validate files exist
    missing = [f for f in nwc_files if not os.path.exists(f)]
    if missing:
        return {"error": "Files not found: {}".format(", ".join(missing))}

    # Method 1: Try plugin (Navisworks running with plugin)
    plugin_available = await asyncio.to_thread(_nw_is_available)
    if plugin_available:
        result = await asyncio.to_thread(
            _nw_call,
            "/aggregate",
            "POST",
            {"inputs": nwc_files, "output": output_path},
            180
        )
        if "error" not in result:
            result["method"] = "plugin"
            return result
        # Fall through to headless if plugin returned error

    # Method 2: Headless via NavisworksBatch.exe
    exe = _find_batch_exe()
    if exe is None:
        return {
            "error": (
                "NavisworksBatch.exe not found. "
                "Please compile NavisworksBatch project in Visual Studio. "
                "Expected path: " + _BATCH_EXE_PATHS[0]
            )
        }

    cmd = [exe, "aggregate", "--inputs"] + nwc_files + ["--output", output_path]

    try:
        def _run_batch():
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                encoding="utf-8",
                errors="replace"
            )
            return proc

        proc = await asyncio.to_thread(_run_batch)

        if proc.returncode == 0:
            return {
                "success": True,
                "method": "headless",
                "appended_count": len(nwc_files),
                "appended": nwc_files,
                "saved_to": output_path,
                "stdout": proc.stdout.strip()
            }
        else:
            return {
                "error": "NavisworksBatch failed (exit {}): {}".format(
                    proc.returncode, proc.stderr.strip() or proc.stdout.strip()
                )
            }

    except subprocess.TimeoutExpired:
        return {"error": "NavisworksBatch.exe timed out (300 s)"}
    except Exception as e:
        return {"error": "Failed to run NavisworksBatch.exe: {}".format(str(e))}


def register_navisworks_aggregate_tools(mcp_server, *args, **kwargs):
    """Register aggregate tools with the MCP server."""
    mcp_server.tool()(nw_aggregate_models)
