#!/usr/bin/env python3
"""
run_pipeline.py — CLI-обёртка для Python 3 пайплайна execute_v2.
Вызывается из IronPython через subprocess.
Читает JSON из stdin, пишет JSON в stdout.

Input JSON:
{
    "request": "найди все стены",
    "session_id": "default",
    "confirm": false,
    "context": {  # опционально, передаётся из IronPython
        "levels": [...],
        "categories": [...],
        "doc_title": "...",
        "doc_path": "..."
    }
}

Output JSON (success):
{
    "status": "ok",
    "code": "...",           # сгенерированный IronPython код
    "intent": "read",
    "requires_confirm": false,
    "session_id": "..."
}

Output JSON (error):
{
    "status": "error",
    "error": "...",
    "code": null
}
"""

from __future__ import annotations

import json
import os
import sys

# Добавляем путь к пакету
_here = os.path.dirname(os.path.abspath(__file__))
_project = os.path.dirname(os.path.dirname(_here))
if _project not in sys.path:
    sys.path.insert(0, _project)

OPENAI_KEY = os.environ.get(
    "OPENAI_API_KEY",
    os.environ.get("OPENROUTER_API_KEY", "")
)

# Пробуем загрузить .env из проекта
_env = os.path.join(_project, ".env")
if os.path.exists(_env):
    for line in open(_env, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ[k.strip()] = v.strip()  # override, не setdefault

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", OPENAI_KEY) or os.environ.get("OPENROUTER_API_KEY", "")


def run(payload: dict) -> dict:
    from revit_mcp.execute_v2.intent_classifier import IntentClassifier, IntentType
    from revit_mcp.execute_v2.code_generator import CodeGenerator
    from revit_mcp.execute_v2.session_state import SessionManager
    from revit_mcp.execute_v2.model_router import ModelRouter

    user_request = payload.get("request", "")
    session_id   = payload.get("session_id", "default")
    confirm      = payload.get("confirm", False)
    revit_context = payload.get("context", {})

    if not user_request:
        return {"status": "error", "error": "No request provided", "code": None}

    # Классификация
    classifier = IntentClassifier()
    intent     = classifier.classify(user_request)
    hints      = {
        "target_category": classifier.extract_target_category(user_request),
        "target_level":    classifier.extract_target_level(user_request, []),
        "target_parameter": classifier.extract_target_parameter(user_request),
    }

    # Требует подтверждения?
    requires_confirm = intent.get("intent_type") == IntentType.WRITE and not confirm
    if requires_confirm:
        return {
            "status": "confirm_required",
            "message": "Операция изменяет модель. Добавьте confirm=true для выполнения.",
            "intent": intent.get("intent_type"),
            "code": None,
        }

    # Генерируем код
    router    = ModelRouter()
    _intent_type = intent.get("intent_type", "read")
    model     = router.route(user_request, _intent_type, 0)
    # Приоритет: OpenRouter ключ (для Gemini/Claude), потом OpenAI
    _or_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    generator = CodeGenerator(api_key=_or_key)
    result    = generator.generate(
        user_request=user_request,
        context=revit_context,
        intent_type=_intent_type,
        hints=hints,
    )

    if result.get("status") == "error":
        return {"status": "error", "error": result.get("error", "Generation failed"), "code": None}

    return {
        "status": "ok",
        "code": result.get("code", ""),
        "intent": intent.get("intent_type", "read"),
        "requires_confirm": False,
        "session_id": session_id,
    }


if __name__ == "__main__":
    try:
        # Читаем как байты и декодируем UTF-8 (stdin может быть cp1251 без -X utf8)
        raw     = sys.stdin.buffer.read()
        payload = json.loads(raw.decode("utf-8"))
        output  = run(payload)
    except Exception as e:
        import traceback
        output = {"status": "error", "error": str(e), "traceback": traceback.format_exc(), "code": None}

    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    # Принудительный выход — openai/httpx создают daemon threads которые мешают выходу
    os._exit(0)
