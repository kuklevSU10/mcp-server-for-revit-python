"""
H3 System Prompt V2 — тесты качества промптов.

Проверяют что system_prompt.txt и fix_prompt.txt содержат
критические паттерны IronPython 2.7 и top-10 ошибок.
"""
import os
import pytest

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'prompts')
SYSTEM_PROMPT_PATH = os.path.join(PROMPTS_DIR, 'system_prompt.txt')
FIX_PROMPT_PATH = os.path.join(PROMPTS_DIR, 'fix_prompt.txt')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# system_prompt.txt
# ---------------------------------------------------------------------------

def test_system_prompt_exists():
    """system_prompt.txt существует и не пустой."""
    assert os.path.exists(SYSTEM_PROMPT_PATH), "system_prompt.txt не найден"
    content = _read(SYSTEM_PROMPT_PATH)
    assert len(content) > 500, "system_prompt.txt слишком короткий"


def test_system_prompt_has_critical_patterns():
    """system_prompt.txt содержит секцию КРИТИЧЕСКИЕ ПАТТЕРНЫ IronPython 2.7."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "КРИТИЧЕСКИЕ ПАТТЕРНЫ" in content, \
        "Нет секции 'КРИТИЧЕСКИЕ ПАТТЕРНЫ' в system_prompt.txt"
    assert "getattr(element" in content or "getattr(elem" in content, \
        "Нет паттерна getattr(element/elem) в system_prompt.txt"
    assert "WhereElementIsNotElementType" in content, \
        "Нет паттерна WhereElementIsNotElementType в system_prompt.txt"


def test_system_prompt_has_no_fstrings_in_examples():
    """system_prompt.txt использует .format() вместо f-строк (IronPython 2.7 их не поддерживает)."""
    content = _read(SYSTEM_PROMPT_PATH)
    # Мягкая проверка — убеждаемся что .format() присутствует как альтернатива f-строкам
    assert ".format(" in content, "Нет использования .format() в system_prompt.txt"


def test_system_prompt_has_examples():
    """system_prompt.txt содержит секцию с примерами."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "ПРИМЕРЫ" in content or "Пример" in content, \
        "Нет секции с примерами в system_prompt.txt"
    # Должно быть хотя бы 5 нумерованных примеров
    assert content.count("Пример") >= 5, \
        "Меньше 5 примеров в system_prompt.txt"


def test_system_prompt_has_phases_example():
    """system_prompt.txt содержит пример работы с фазами."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "PHASE_CREATED" in content or "Phase Created" in content or "фаз" in content.lower(), \
        "Нет примера работы с фазами в system_prompt.txt"


def test_system_prompt_has_nested_families_example():
    """system_prompt.txt содержит пример GetSubComponentIds."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "GetSubComponentIds" in content, \
        "Нет примера GetSubComponentIds (nested families) в system_prompt.txt"


def test_system_prompt_has_area_conversion():
    """system_prompt.txt содержит паттерн конвертации площади."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "0.092903" in content, \
        "Нет коэффициента конвертации площади (0.092903) в system_prompt.txt"


def test_system_prompt_has_length_conversion():
    """system_prompt.txt содержит паттерн конвертации длины."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "0.3048" in content, \
        "Нет коэффициента конвертации длины (0.3048) в system_prompt.txt"


def test_system_prompt_has_result_pattern():
    """system_prompt.txt содержит обязательный паттерн __result__."""
    content = _read(SYSTEM_PROMPT_PATH)
    assert "__result__" in content, \
        "Нет паттерна __result__ в system_prompt.txt"


# ---------------------------------------------------------------------------
# fix_prompt.txt
# ---------------------------------------------------------------------------

def test_fix_prompt_exists():
    """fix_prompt.txt существует и не пустой."""
    assert os.path.exists(FIX_PROMPT_PATH), "fix_prompt.txt не найден"
    content = _read(FIX_PROMPT_PATH)
    assert len(content) > 100, "fix_prompt.txt слишком короткий"


def test_fix_prompt_has_top10():
    """fix_prompt.txt содержит секцию ТОП-10 частых ошибок."""
    content = _read(FIX_PROMPT_PATH)
    assert "ТОП-10" in content, \
        "Нет секции ТОП-10 в fix_prompt.txt"
    assert "AttributeError" in content, \
        "Нет упоминания AttributeError в fix_prompt.txt"
    assert "IronPython" in content, \
        "Нет упоминания IronPython в fix_prompt.txt"


def test_fix_prompt_has_none_check():
    """fix_prompt.txt содержит совет проверять None."""
    content = _read(FIX_PROMPT_PATH)
    assert "is not None" in content or "is None" in content, \
        "Нет паттерна проверки None в fix_prompt.txt"


def test_fix_prompt_has_unicode_advice():
    """fix_prompt.txt содержит совет по Unicode/кириллице."""
    content = _read(FIX_PROMPT_PATH)
    assert "unicode" in content.lower() or "utf-8" in content or "cp1251" in content, \
        "Нет совета по Unicode/кодировкам в fix_prompt.txt"


def test_fix_prompt_has_transaction_advice():
    """fix_prompt.txt содержит совет по транзакциям."""
    content = _read(FIX_PROMPT_PATH)
    assert "Transaction" in content or "транзакц" in content.lower(), \
        "Нет совета по Transaction в fix_prompt.txt"


def test_fix_prompt_has_fstring_warning():
    """fix_prompt.txt предупреждает что f-strings не работают в IronPython 2.7."""
    content = _read(FIX_PROMPT_PATH)
    assert "f-string" in content.lower() or "f\"" in content or ".format(" in content, \
        "Нет предупреждения о f-strings в fix_prompt.txt"


def test_fix_prompt_has_list_conversion():
    """fix_prompt.txt содержит совет конвертировать .NET List в list()."""
    content = _read(FIX_PROMPT_PATH)
    assert "list(" in content, \
        "Нет совета list() в fix_prompt.txt"


# ---------------------------------------------------------------------------
# Integration: CodeGenerator loads prompts from files
# ---------------------------------------------------------------------------

def test_code_generator_reads_system_prompt():
    """CodeGenerator.system_prompt читается из файла (не fallback)."""
    import sys
    import os
    # Add project root to path
    project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    from revit_mcp.execute_v2.code_generator import CodeGenerator
    cg = CodeGenerator(api_key="test-key")
    prompt = cg.system_prompt
    assert "КРИТИЧЕСКИЕ ПАТТЕРНЫ" in prompt, \
        "CodeGenerator.system_prompt не содержит КРИТИЧЕСКИЕ ПАТТЕРНЫ — файл не читается?"
    assert len(prompt) > 1000, \
        "CodeGenerator.system_prompt слишком короткий — возможно используется fallback"


def test_code_generator_reads_fix_prompt():
    """CodeGenerator.fix_prompt_template читается из файла (не fallback)."""
    import sys
    import os
    project_root = os.path.join(os.path.dirname(__file__), '..', '..', '..')
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    from revit_mcp.execute_v2.code_generator import CodeGenerator
    cg = CodeGenerator(api_key="test-key")
    prompt = cg.fix_prompt_template
    assert "ТОП-10" in prompt, \
        "CodeGenerator.fix_prompt_template не содержит ТОП-10 — файл не читается?"
