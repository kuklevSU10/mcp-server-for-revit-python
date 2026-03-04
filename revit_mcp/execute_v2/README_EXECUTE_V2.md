# KUKAI execute_v2 — Архитектура и Документация

`execute_v2` — это ядро системы KUKAI, позволяющее выполнять запросы к Revit API на естественном языке, транслируя их в безопасный IronPython 2.7 код.

## Архитектура Pipeline

Основной класс `ExecuteV2Pipeline` реализует следующий процесс:

1. **Intent Classification** (`IntentClassifier`): 
   Определяет тип запроса: `read`, `write`, `analyze`, `view_op`, `dangerous`. Извлекает намерения (категория, параметр, уровень) для подсказок (hints).
2. **Context Building** (`ContextBuilder` + `ContextCache`):
   Собирает метаданные из Revit (уровни, виды, рабочие наборы, параметры). `read` и `analyze` запросы используют быстрый минимальный контекст.
3. **Template Library** (`TemplateLibrary`):
   Применяет проверенные шаблоны (20+ шт), если задача типичная (сводки, спецификации и т.п.).
4. **Code Generation** (`CodeGenerator` + `ModelRouter` + `CodeCache`):
   Определяет нужную LLM-модель (`fast` = Gemini Flash, `smart` = Sonnet). Генерирует или достаёт из кэша IronPython 2.7 код.
5. **Sandbox Validation** (`SandboxValidator`):
   Статический анализ AST. Блокирует опасные паттерны (`import threading`, `System.Reflection`, `from X import *`, и т.д.).
6. **Execution** (`TransactionExecutor` + `timeout_instrumenter`):
   Безопасное выполнение в `exec()` с оберткой циклов `for/while` счетчиком против зависаний. Транзакции создаются автоматически.
7. **Retry & Error Handling** (`RetryLoop`):
   Анализирует Traceback и исключения (.NET/IronPython). Дает умные подсказки (hints) LLM для исправления (max 3 попытки).
8. **Formatting & Session State** (`ResultFormatter`, `SessionState`):
   Формирует читаемый ответ. Сохраняет историю диалога и `ElementId` для многошаговых запросов.
9. **Audit Logging** (`AuditLog`):
   Пишет метрики и хэши запросов в `jsonl` файлы для аналитики.

## Многошаговые операции (Multi-Step)

Если запрос сложный ("сначала найди... а потом удали..."), он разбивается через `MultiStepExecutor` на шаги.
Шаги выполняются последовательно. Результат первого шага (`ElementId`) через `SessionState` передается во второй шаг.
В случае ошибки на любом шаге — весь процесс откатывается (RollBack) через `TransactionGroup`.

## Инструкции по разработке

### Запуск тестов

Тесты написаны на `pytest` и не требуют живого Revit для запуска (используют mock-объекты):
```bash
cd mcp-server-for-revit-python/revit_mcp/execute_v2/
python -m pytest tests/ -v
```

### Как добавить новый шаблон
Все шаблоны лежат в `templates/templates.json`.
Чтобы добавить новый, просто впишите его структуру:
```json
{
  "id": "my_new_template",
  "name": "Описание",
  "description": "Что делает",
  "intent_type": "read",
  "keywords": ["слова", "маркеры"],
  "code": "result = DB.FilteredElementCollector(doc)... \n__result__ = {'summary': 'Ok', 'count': len(result)}"
}
```
**Важно для IronPython 2.7:**
- Нет f-strings (используйте `"{...}".format(...)`).
- Нет type hints.
- Коллекции .NET нужно оборачивать в `list()`.

### Примеры API запросов
Endpoint: `POST /execute_v2/`
```json
{
  "request": "переименуй все двери на 1 этаже, добавь префикс Д-",
  "session_id": "user-session-123",
  "confirm": false
}
```
Ответ:
```json
{
  "status": "success",
  "response": "Переименовано 12 дверей",
  "intent": { "intent_type": "write", "confidence": 0.9 },
  "retries": 0,
  "code_executed": "... python code ...",
  "model_used": "anthropic/claude-sonnet-4-6"
}
```

## Troubleshooting
- **Код падает с KeyError:** Проверьте, не используются ли голые `{}` в шаблонах/строках, которые идут через `.format()`. Используйте двойные `{{}}`.
- **Revit падает:** Код запрашивает методы из других потоков. Убедитесь, что `import threading` заблокирован в sandbox.
- **Откат транзакций:** Не пишите явные `Transaction.Start()` в генерируемом коде. `TransactionExecutor` сам открывает и закрывает транзакции.