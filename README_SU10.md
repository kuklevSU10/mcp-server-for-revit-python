# mcp-server-for-revit-python — СУ-10 Fork

> Форк: [kuklevSU10/mcp-server-for-revit-python](https://github.com/kuklevSU10/mcp-server-for-revit-python)  
> Upstream: [mcp-servers-for-revit/mcp-server-for-revit-python](https://github.com/mcp-servers-for-revit/mcp-server-for-revit-python)

## Что добавлено vs upstream

### Новые custom_tools/ (13 инструментов)

| Tool | Описание |
|------|----------|
| `bim_catalog` | Каталог всех типов элементов с семантическим распознаванием |
| `bim_inspect` | Детальные параметры отдельного элемента |
| `bim_search` | Семантический поиск элементов + colorize |
| `bim_summary` | Сводка модели: архитектура / конструктив / ОВиК |
| `bim_volumes` | Объёмы по категориям (group_by level/type/material) |
| `bim_to_vor` | Маппинг BIM → ВОР (configurable mapping JSON) |
| `bim_vor_generate` | Генерация ВОР из BIM через паттерны |
| `bim_vor_to_sheets` | BIM → ВОР → Google Sheets |
| `vor_vs_bim` | Верификация ВОР заказчика (Excel или JSON) |
| `bim_audit` | Аудит модели (5 проверок) |
| `bim_report` | Тендерный отчёт Markdown |
| `bim_export` | Экспорт в Excel (.xlsx) |
| `bim_links` | Работа со связанными файлами |
| `bim_query` | NL поиск элементов |

### BIM Semantic Layer
- `bim-semantic-layer/global_patterns.json` — 140+ паттернов классификации
- `custom_tools/_scan_engine.py` — движок семантического матчинга
- `custom_tools/_constants.py` — единый реестр 30 категорий Revit

### Исправления upstream
- `httpx` → `requests` (несовместимость с pyRevit Routes)
- `get_revit_view` через `execute_code` (кириллица в именах видов)
- `startup.py` — очистка `sys.modules` для стабильной перезагрузки

---

## Установка с нуля

### 1. Требования
- Windows 10/11
- Python 3.10+ (`python --version`)
- Autodesk Revit 2023/2024/2026
- pyRevit 6.1.0+ ([releases](https://github.com/pyrevitlabs/pyRevit/releases))
- Git

### 2. pyRevit Routes Server
```
Revit → вкладка pyRevit → Settings → Routes → Enable
Port: 48884 → Reload pyRevit
```
Проверка: `curl http://localhost:48884/revit_mcp/status/`

### 3. Клонировать и настроить
```powershell
cd C:\Users\<user>\clawd\projects\revit-openclaw
git clone https://github.com/kuklevSU10/mcp-server-for-revit-python.git
cd mcp-server-for-revit-python

# Установить зависимости
pip install mcp fastmcp requests openpyxl google-api-python-client google-auth-oauthlib openai numpy

# Скопировать extension в pyRevit
$ext = "$env:APPDATA\pyRevit\Extensions\revit-mcp-python.extension"
New-Item -ItemType Directory -Path $ext -Force
Copy-Item "revit_mcp" $ext -Recurse -Force
Copy-Item "startup.py" $ext -Force

# Перезагрузить pyRevit в Revit (вкладка pyRevit → Reload)
```

### 4. Запуск MCP сервера
```powershell
python main.py --combined
# или через mcporter:
# Добавить в mcporter.json конфиг (см. ниже)
```

### 5. Проверка
```python
# tools/test_mcp_status.py
python C:\...\clawd\tools\test_mcp_status.py
# Ожидаем: Status: active | Health: healthy
```

---

## Конфигурация mcporter

`C:\Users\<user>\clawd\config\mcporter.json`:
```json
{
  "mcpServers": {
    "revit-mcp": {
      "command": "python",
      "args": ["C:\\...\\mcp-server-for-revit-python\\main.py", "--combined"]
    }
  }
}
```

---

## Структура проекта

```
mcp-server-for-revit-python/
├── main.py                  # FastMCP сервер (точка входа)
├── tools/                   # Upstream tools (не изменять)
│   ├── view_tools.py        # get_revit_view (переписан для кириллики)
│   └── ...
├── custom_tools/            # Наши тендерные tools
│   ├── _constants.py        # Реестр категорий Revit
│   ├── _scan_engine.py      # BIM Semantic Layer движок
│   ├── _validation.py       # Валидация входных данных
│   ├── bim_catalog.py
│   ├── bim_summary.py
│   ├── bim_volumes.py
│   ├── bim_to_vor.py
│   ├── bim_vor_to_sheets.py # → Google Sheets
│   ├── vor_vs_bim.py        # Excel ВОР загрузка
│   ├── bim_audit.py         # 5 checks
│   ├── bim_report.py
│   ├── bim_export.py
│   ├── bim_links.py
│   ├── bim_query.py
│   └── mappings/
│       └── default_mapping.json
├── revit_mcp/               # pyRevit Extension (IronPython)
│   ├── startup.py           # Точка входа extension
│   ├── status.py
│   ├── views.py
│   ├── colors.py
│   ├── code_execution.py
│   └── utils.py
├── bim-semantic-layer/      # Семантический слой
│   └── global_patterns.json # 140+ паттернов
└── upstream-sync.ps1        # Синхронизация с upstream
```

---

## Добавить новый custom tool

1. Создать `custom_tools/my_tool.py`:
```python
# -*- coding: utf-8 -*-
from mcp.server.fastmcp import Context
from ._constants import CATEGORY_REGISTRY

def register_my_tools(mcp_server, revit_get, revit_post, revit_image):
    @mcp_server.tool()
    async def my_tool(param: str = "", ctx: Context = None) -> dict:
        """Tool description."""
        code = "import json\nprint(json.dumps({'result': 'hello'}))\n"
        resp = await revit_post("/execute_code/", {"code": code}, ctx)
        return resp
```

2. Зарегистрировать в `custom_tools/__init__.py`:
```python
from .my_tool import register_my_tools
# В register_custom_tools():
register_my_tools(mcp, revit_get, revit_post, revit_image)
```

3. Перезапустить MCP сервер (`python main.py --combined`)

---

## Upstream sync

```powershell
# Обновить с upstream без потери наших tools
.\upstream-sync.ps1

# Проверить есть ли новые коммиты в upstream
git fetch upstream
git log HEAD..upstream/master --oneline
```

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `RouteHandlerNotDefinedException` | Reload Scripts в Revit (pyRevit → Reload) |
| `execute_code` таймаут | Полный рестарт Revit (не Reload Scripts) |
| Кириллица в видах не работает | Использовать `get_revit_view` через MCP (execute_code внутри) |
| `httpx` ошибки | Убедиться что установлен `requests`, не `httpx` |
| 0 routes registered | Проверить `startup.py` в pyRevit → очистка sys.modules |
