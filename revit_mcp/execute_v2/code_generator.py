"""
Code Generator — calls LLM to generate IronPython code for Revit.

Runs on Python 3 side (MCP server). Uses OpenRouter API.
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, Optional

import requests


# Directory containing prompt templates
PROMPTS_DIR = Path(__file__).parent / "prompts"


class CodeGenerator:
    """
    Generates IronPython code via LLM for Revit execution.
    
    Models (priority):
        1. google/gemini-3-flash-preview — fast, cheap (default)
        2. anthropic/claude-sonnet-4-6 — for complex requests
    """

    OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
    OPENAI_URL     = "https://api.openai.com/v1/chat/completions"
    
    DEFAULT_MODEL = "google/gemini-3-flash-preview"
    COMPLEX_MODEL = "anthropic/claude-sonnet-4-6"

    def __init__(self, api_url=None, api_key=None):
        """
        Args:
            api_url: KUKAI backend URL (future use). Falls back to OpenAI.
            api_key: API key. Falls back to OPENROUTER_API_KEY or OPENAI_API_KEY env var.
        """
        self.api_url = api_url
        self.api_key = (
            api_key
            or os.environ.get("OPENROUTER_API_KEY", "")
            or os.environ.get("OPENAI_API_KEY", "")
        )
        self._system_prompt = None
        self._fix_prompt_template = None

    @property
    def system_prompt(self):
        """Lazy-load system prompt from file."""
        if self._system_prompt is None:
            prompt_path = PROMPTS_DIR / "system_prompt.txt"
            if prompt_path.exists():
                self._system_prompt = prompt_path.read_text(encoding="utf-8")
            else:
                self._system_prompt = "You are a Revit API expert. Generate IronPython 2.7 code."
        return self._system_prompt

    @property
    def fix_prompt_template(self):
        """Lazy-load fix prompt template from file."""
        if self._fix_prompt_template is None:
            prompt_path = PROMPTS_DIR / "fix_prompt.txt"
            if prompt_path.exists():
                self._fix_prompt_template = prompt_path.read_text(encoding="utf-8")
            else:
                self._fix_prompt_template = (
                    "Fix this code. Error: {error_type}: {error_message}\n"
                    "Code:\n{original_code}\n"
                )
        return self._fix_prompt_template

    def generate(
        self,
        user_request: str,
        context: dict,
        intent_type: str,
        hints: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate IronPython code from user request.

        Args:
            user_request: Natural language request.
            context: Revit model context dict (from ContextBuilder).
            intent_type: Intent classification (read/write/view_op/dangerous).
            hints: Optional dict with target_category, target_level, target_parameter
                   extracted by IntentClassifier.

        Returns:
            {"code": "...", "model_used": "...", "tokens": N}
        """
        # Select model
        model = self.COMPLEX_MODEL if intent_type == "complex" else self.DEFAULT_MODEL

        # Build hints section if any hints are present
        hints_text = ""
        if hints and any(hints.values()):
            hints_text = "\n## CONTEXT HINTS (используй эти данные в коде)\n"
            if hints.get("target_category"):
                hints_text += "- Целевая категория: {} (BuiltInCategory)\n".format(
                    hints["target_category"]
                )
            if hints.get("target_level"):
                hints_text += "- Целевой уровень: '{}'\n".format(hints["target_level"])
            if hints.get("target_parameter"):
                hints_text += "- Целевой параметр: '{}'\n".format(hints["target_parameter"])

        # Build user message with context
        context_json = json.dumps(context, ensure_ascii=False, indent=2)
        user_message = (
            "Контекст модели Revit:\n```json\n{}\n```\n\n"
            "Тип операции: {}\n{}\n"
            "Запрос пользователя: {}"
        ).format(context_json, intent_type, hints_text, user_request)

        # Call LLM
        response = self._call_llm(
            model=model,
            system=self.system_prompt,
            user_message=user_message,
        )

        code = self._extract_code(response.get("content", ""))
        return {
            "code": code,
            "model_used": model,
            "tokens": response.get("tokens", 0),
            "raw_response": response.get("content", ""),
        }

    def fix(self, original_code: str, error_info: dict, context: dict = None) -> Dict:
        """
        Fix code that produced an error.

        Args:
            original_code: The code that failed.
            error_info: Dict with error_type, error_message, output (traceback).
            context: Optional Revit model context dict (helps LLM understand the model).

        Returns:
            {"code": "...", "model_used": "...", "tokens": N}
        """
        # Build fix prompt from template
        fix_message = self.fix_prompt_template.format(
            error_type=error_info.get("error_type", "Unknown"),
            error_message=error_info.get("error_message", "Unknown error"),
            traceback=error_info.get("output", ""),
            hints="Check IronPython 2.7 compatibility. No f-strings, no type hints.",
            original_code=original_code,
        )

        # Inject model context if available
        if context:
            context_json = json.dumps(context, ensure_ascii=False, indent=2)
            fix_message += "\n\nРевит контекст модели:\n```json\n{}\n```".format(context_json)

        model = self.DEFAULT_MODEL
        response = self._call_llm(
            model=model,
            system=self.system_prompt,
            user_message=fix_message,
        )

        code = self._extract_code(response.get("content", ""))
        return {
            "code": code,
            "model_used": model,
            "tokens": response.get("tokens", 0),
        }

    def _call_llm(self, model: str, system: str, user_message: str) -> Dict:
        """
        Call OpenRouter API.

        Returns:
            {"content": "...", "tokens": N}
        """
        if not self.api_key:
            raise ValueError(
                "No API key provided. Set OPENROUTER_API_KEY env var or pass api_key to CodeGenerator."
            )

        headers = {
            "Authorization": "Bearer {}".format(self.api_key),
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
            "max_tokens": 4096,
        }

        try:
            resp = requests.post(
                self.OPENAI_URL,
                headers=headers,
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()

            content = ""
            if "choices" in data and data["choices"]:
                content = data["choices"][0].get("message", {}).get("content", "")

            tokens = 0
            if "usage" in data:
                tokens = data["usage"].get("total_tokens", 0)

            return {"content": content, "tokens": tokens}

        except requests.exceptions.RequestException as e:
            return {
                "content": "",
                "tokens": 0,
                "error": str(e),
            }

    @staticmethod
    def _extract_code(llm_response: str) -> str:
        """
        Extract Python/IronPython code from LLM response.

        Tries (in order):
            1. ```python ... ``` block
            2. ```ironpython ... ``` block
            3. ``` ... ``` block (generic)
            4. Entire response as code
        """
        if not llm_response:
            return ""

        # Try ```python or ```ironpython blocks
        patterns = [
            r'```(?:python|ironpython)\s*\n(.*?)```',
            r'```\s*\n(.*?)```',
        ]

        for pattern in patterns:
            match = re.search(pattern, llm_response, re.DOTALL)
            if match:
                return match.group(1).strip()

        # If no code block found, return the whole response stripped
        # (LLM sometimes returns just code without fences)
        return llm_response.strip()
