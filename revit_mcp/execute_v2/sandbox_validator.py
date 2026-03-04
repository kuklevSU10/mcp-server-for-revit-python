"""
Sandbox Validator — regex-based static analysis for IronPython code.

Blocks dangerous imports, system calls, file operations, and destructive Revit operations.
Runs on Python 3 side (MCP server), validates code BEFORE sending to Revit.
"""

import re
from typing import Dict


class SandboxValidator:
    """Validates IronPython code against a blocklist of dangerous patterns."""

    MAX_CODE_LENGTH = 50_000  # 50K characters

    # Each tuple: (compiled_regex, human-readable reason)
    BLOCKED_PATTERNS = [
        # --- Python dangerous imports ---
        (re.compile(r'\bimport\s+os\b'), "Import of 'os' module is blocked"),
        (re.compile(r'\bfrom\s+os\b'), "Import from 'os' module is blocked"),
        (re.compile(r'\bimport\s+subprocess\b'), "Import of 'subprocess' module is blocked"),
        (re.compile(r'\bfrom\s+subprocess\b'), "Import from 'subprocess' module is blocked"),
        (re.compile(r'\bimport\s+sys\b'), "Import of 'sys' module is blocked"),
        (re.compile(r'\bfrom\s+sys\b'), "Import from 'sys' module is blocked"),
        (re.compile(r'\bimport\s+shutil\b'), "Import of 'shutil' module is blocked"),
        (re.compile(r'\bfrom\s+shutil\b'), "Import from 'shutil' module is blocked"),

        # --- .NET dangerous namespaces ---
        (re.compile(r'\bSystem\.IO\b'), "Access to System.IO is blocked"),
        (re.compile(r'\bSystem\.Net\b'), "Access to System.Net is blocked"),
        (re.compile(r'\bSystem\.Diagnostics\b'), "Access to System.Diagnostics is blocked"),
        (re.compile(r'\bSystem\.Reflection\b'), "Access to System.Reflection is blocked"),

        # --- Dynamic execution / introspection ---
        (re.compile(r'\b__import__\s*\('), "Use of __import__() is blocked"),
        (re.compile(r'(?<!\w)open\s*\('), "Use of open() is blocked"),
        (re.compile(r'(?<!\w)file\s*\('), "Use of file() is blocked"),
        (re.compile(r'\bexec\s*\('), "Use of exec() is blocked"),
        (re.compile(r'\beval\s*\('), "Use of eval() is blocked"),

        # --- IronPython CLR ---
        (re.compile(r'\bclr\.AddReference\b'), "Use of clr.AddReference() is blocked"),

        # --- Threading (Revit API is not thread-safe) ---
        (re.compile(r'\bimport\s+threading\b'), "Import of 'threading' is blocked — Revit API is not thread-safe"),
        (re.compile(r'\bfrom\s+threading\b'), "Import from 'threading' is blocked"),
        (re.compile(r'\bimport\s+multiprocessing\b'), "Import of 'multiprocessing' is blocked"),

        # --- Wildcard imports (break Python builtins namespace) ---
        (re.compile(r'\bfrom\s+\S+\s+import\s+\*'), "Wildcard import is blocked — breaks builtins namespace"),

        # --- Dangerous introspection ---
        (re.compile(r'\b__subclasses__\b'), "Access to __subclasses__ is blocked"),
        (re.compile(r'\b__globals__\b'), "Access to __globals__ is blocked"),
        (re.compile(r'\b__class__\b'), "Access to __class__ is blocked"),
        (re.compile(r'\bSystem\.AppDomain\b'), "Access to System.AppDomain is blocked"),
        (re.compile(r'\bProcess\.Start\b'), "Process.Start is blocked"),

        # --- Dangerous Revit operations ---
        (re.compile(r'\bdoc\.Delete\b'), "doc.Delete is always blocked — use safe wrappers"),
        (re.compile(r'\bApplication\.OpenDocumentFile\b'), "Application.OpenDocumentFile is blocked"),
    ]

    def validate(self, code: str) -> Dict:
        """
        Validate IronPython code for safety.

        Returns:
            {"valid": True} or {"valid": False, "reason": "...", "blocked_pattern": "...", "all_errors": [...]}
        """
        errors = []

        if len(code) > self.MAX_CODE_LENGTH:
            errors.append({
                "reason": "Code exceeds maximum length of {} characters (got {})".format(
                    self.MAX_CODE_LENGTH, len(code)
                ),
                "blocked_pattern": "code_length > {}".format(self.MAX_CODE_LENGTH),
            })

        for pattern, reason in self.BLOCKED_PATTERNS:
            match = pattern.search(code)
            if match:
                errors.append({
                    "reason": reason,
                    "blocked_pattern": match.group(0),
                })

        if errors:
            return {
                "valid": False,
                "reason": errors[0]["reason"],           # первая ошибка для совместимости
                "blocked_pattern": errors[0]["blocked_pattern"],
                "all_errors": errors,                    # все ошибки
            }
        return {"valid": True}
