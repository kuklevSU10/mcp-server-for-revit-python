"""
Intent Classifier — rule-based, instant classification of user requests.

Determines whether a request is read, write, view_op, or dangerous.
No LLM calls — pure keyword matching with priority ordering.
"""

import re
from typing import Dict, List, Optional, Tuple


class IntentType:
    """Intent type constants."""
    READ = "read"
    WRITE = "write"
    VIEW_OP = "view_op"
    DANGEROUS = "dangerous"
    ANALYZE = "analyze"


class IntentClassifier:
    """
    Rule-based classifier for Revit user requests.
    
    Priority order: DANGEROUS > WRITE > VIEW_OP > READ (default).
    Supports Russian and English keywords.
    """

    # (intent_type, confidence, keywords_list)
    # Order matters: first match wins (DANGEROUS checked first)
    KEYWORD_RULES: List[Tuple[str, float, List[str]]] = [
        # --- DANGEROUS ---
        (IntentType.DANGEROUS, 0.95, [
            # Russian
            "удали", "удалить", "удаление", "снеси", "снести",
            "очисти", "очистить", "очистка", "уничтожь", "уничтожить",
            "стереть", "сотри", "разрушь",
            # English
            "delete", "remove", "purge", "wipe", "destroy", "erase",
            "demolish", "obliterate",
        ]),
        # --- WRITE ---
        (IntentType.WRITE, 0.90, [
            # Russian — общие
            "переименуй", "переименовать", "измени", "изменить",
            "установи", "установить", "задай", "задать",
            "создай", "создать", "перемести", "переместить",
            "копируй", "копировать", "скопируй", "поверни", "повернуть",
            "назначь", "назначить", "добавь", "добавить",
            "обнови", "обновить", "замени", "заменить",
            "присвой", "присвоить", "запиши", "записать",
            "заполни", "заполнить", "проставь", "пронумеруй",
            "расставь", "разместить", "разместь", "нарисуй",
            # Russian — строительные/BIM
            "промаркируй", "промаркировать", "пометь", "отметь",
            "привяжи", "привязать", "зафиксируй",
            "скорректируй", "исправь", "поправь",
            # English
            "rename", "set", "create", "move", "copy", "rotate",
            "assign", "update", "modify", "change", "add", "place",
            "mirror", "flip", "swap", "replace", "write",
            "number", "tag", "mark", "stamp", "populate", "fill",
        ]),
        # --- ANALYZE ---
        (IntentType.ANALYZE, 0.88, [
            # Russian — аналитика
            "сравни", "сравнить", "сопоставь",
            "проанализируй", "анализ", "аналитика",
            "ведомость", "спецификация", "сводка",
            "сгруппируй", "сгруппировать",
            "итого", "суммируй", "суммарно",
            "процент", "доля", "соотношение",
            "вор", "vor", "объёмы", "объемы", "площади",
            "распределение", "статистика по",
            # English
            "analyze", "analyse", "summarize", "breakdown",
            "group by", "aggregate", "distribution",
            "statistics", "report on", "schedule for",
            "compare", "ratio", "percentage",
        ]),
        # --- VIEW_OP ---
        (IntentType.VIEW_OP, 0.85, [
            # Russian phrases and words
            "покажи вид", "активируй", "перейди на", "перейти на",
            "изолируй", "изолировать", "скрой", "скрыть",
            "выдели", "выделить", "подсвети", "подсветить",
            "приблизь", "отдали", "масштабируй",
            "открой вид", "переключи вид",
            # English
            "zoom", "isolate", "hide", "unhide",
            "select", "navigate", "activate view",
            "show view", "switch view", "focus on",
            "highlight", "pan to",
        ]),
    ]

    # READ keywords — used only for confidence boost (READ is the default)
    READ_KEYWORDS: List[str] = [
        # Russian — общие
        "найди", "найти", "покажи список", "покажи",
        "подсчитай", "подсчитать", "посчитай", "посчитать",
        "сколько", "какие", "какой", "какая",
        "выведи", "вывести", "перечисли",
        "проверь", "проверить", "анализируй",
        "информация", "данные", "статистика",
        # Russian — BIM/строительные
        "список стен", "список перекрытий", "список помещений",
        "список дверей", "список окон", "список колонн",
        "площадь", "длина", "объём", "объем",
        "уровень", "этаж", "секция",
        "марка", "тип", "семейство",
        "параметры элемента", "параметры стены",
        "предупреждения", "ошибки модели",
        "несущие", "ограждающие", "конструкции",
        # English
        "find", "list", "count", "show", "get",
        "what", "which", "how many", "display",
        "check", "verify", "analyze", "query",
        "report", "summarize", "info",
        "walls", "floors", "rooms", "doors", "windows", "columns",
        "area", "length", "volume", "level", "type",
    ]

    # Category mapping: RU/EN keyword → Revit BuiltInCategory
    CATEGORY_MAP: Dict[str, str] = {
        # Russian → Revit BuiltInCategory
        "двер": "OST_Doors",
        "дверь": "OST_Doors",
        "двери": "OST_Doors",
        "окн": "OST_Windows",
        "окно": "OST_Windows",
        "окна": "OST_Windows",
        "окон": "OST_Windows",
        "стен": "OST_Walls",
        "стена": "OST_Walls",
        "стены": "OST_Walls",
        "перекрыт": "OST_Floors",
        "перекрытие": "OST_Floors",
        "перекрытия": "OST_Floors",
        "помещени": "OST_Rooms",
        "помещение": "OST_Rooms",
        "комнат": "OST_Rooms",
        "колонн": "OST_Columns",
        "колонна": "OST_Columns",
        "несущ колонн": "OST_StructuralColumns",
        "балк": "OST_StructuralFraming",
        "балка": "OST_StructuralFraming",
        "балки": "OST_StructuralFraming",
        "кровл": "OST_Roofs",
        "кровля": "OST_Roofs",
        "лестниц": "OST_Stairs",
        "лестница": "OST_Stairs",
        "мебел": "OST_Furniture",
        "мебель": "OST_Furniture",
        "сантехник": "OST_PlumbingFixtures",
        "светильник": "OST_LightingFixtures",
        "воздуховод": "OST_DuctCurves",
        "труб": "OST_PipeCurves",
        "трубопровод": "OST_PipeCurves",
        "решетк": "OST_DuctTerminal",
        "зон": "OST_Zones",
        "зона": "OST_Zones",
        "пространств": "OST_Spaces",
        "пространство": "OST_Spaces",
        "ось": "OST_Grids",
        "оси": "OST_Grids",
        "сетк": "OST_Grids",
        "уровень": "OST_Levels",
        "этаж": "OST_Levels",
        "этажи": "OST_Levels",
        # English keys
        "door": "OST_Doors",
        "doors": "OST_Doors",
        "window": "OST_Windows",
        "windows": "OST_Windows",
        "wall": "OST_Walls",
        "walls": "OST_Walls",
        "floor": "OST_Floors",
        "floors": "OST_Floors",
        "room": "OST_Rooms",
        "rooms": "OST_Rooms",
        "column": "OST_Columns",
        "columns": "OST_Columns",
        "beam": "OST_StructuralFraming",
        "beams": "OST_StructuralFraming",
        "roof": "OST_Roofs",
        "stair": "OST_Stairs",
        "stairs": "OST_Stairs",
        "furniture": "OST_Furniture",
        "grid": "OST_Grids",
        "grids": "OST_Grids",
        "level": "OST_Levels",
        "levels": "OST_Levels",
    }

    def __init__(self):
        # Pre-compile patterns for each rule
        self._compiled_rules = []
        for intent_type, confidence, keywords in self.KEYWORD_RULES:
            patterns = [re.compile(r'\b{}\b'.format(re.escape(kw)), re.IGNORECASE | re.UNICODE)
                       for kw in keywords]
            self._compiled_rules.append((intent_type, confidence, keywords, patterns))

        self._read_patterns = [
            re.compile(r'\b{}\b'.format(re.escape(kw)), re.IGNORECASE | re.UNICODE)
            for kw in self.READ_KEYWORDS
        ]

        # Pre-sort category keys by length (longer first) to match more specific keys first
        self._category_keys_sorted = sorted(
            self.CATEGORY_MAP.keys(), key=len, reverse=True
        )

    def classify(self, user_request: str) -> Dict:
        """
        Classify user request intent.

        Args:
            user_request: Natural language request (RU or EN).

        Returns:
            {
                "intent_type": "write",
                "confidence": 0.9,
                "detected_keywords": ["переименуй"],
                "hints": {
                    "target_category": "OST_Doors",  # None if not detected
                    "target_level": "Level 1",         # None if not detected
                    "target_parameter": "Mark",        # None if not detected
                }
            }
        """
        if not user_request or not user_request.strip():
            return {
                "intent_type": IntentType.READ,
                "confidence": 0.5,
                "detected_keywords": [],
                "hints": {
                    "target_category": None,
                    "target_level": None,
                    "target_parameter": None,
                },
            }

        text = user_request.lower().strip()

        # Check rules in priority order: DANGEROUS > WRITE > VIEW_OP
        base_result = None
        for intent_type, confidence, keywords, patterns in self._compiled_rules:
            detected = []
            for kw, pattern in zip(keywords, patterns):
                if pattern.search(text):
                    detected.append(kw)
            if detected:
                base_result = {
                    "intent_type": intent_type,
                    "confidence": confidence,
                    "detected_keywords": detected,
                }
                break

        if base_result is None:
            # Check READ keywords for confidence boost
            read_detected = []
            for kw, pattern in zip(self.READ_KEYWORDS, self._read_patterns):
                if pattern.search(text):
                    read_detected.append(kw)

            base_result = {
                "intent_type": IntentType.READ,
                "confidence": 0.8 if read_detected else 0.5,
                "detected_keywords": read_detected,
            }

        # Extract hints
        hints = {
            "target_category": self.extract_target_category(user_request),
            "target_level": self.extract_target_level(user_request),
            "target_parameter": self.extract_target_parameter(user_request),
        }
        base_result["hints"] = hints

        return base_result

    def extract_target_category(self, request: str) -> Optional[str]:
        """
        Извлечь целевую категорию из запроса.
        
        Возвращает Revit BuiltInCategory имя (например, 'OST_Doors') или None.
        Проверяет ключи из CATEGORY_MAP как подстроки (ключи — это основы/стемы слов).
        Более длинные ключи проверяются первыми для точности.
        """
        if not request:
            return None

        text_lower = request.lower()

        # Simple substring match: keys are stems/prefixes of Russian words,
        # so substring match is the correct approach (e.g. "двер" matches "дверей").
        # Longer keys are checked first to prefer specific matches.
        for key in self._category_keys_sorted:
            if key in text_lower:
                return self.CATEGORY_MAP[key]

        return None

    def extract_target_level(
        self,
        request: str,
        available_levels: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Найти упоминание уровня в запросе.
        
        Ищет паттерны типа 'этаж 3', '1 этаж', 'Level 1', 'уровень 2'.
        Если передан available_levels — ищет прямое совпадение имени уровня в тексте.
        
        Returns:
            Строка с номером уровня (например, '1', '2', '3') или
            полное имя уровня (если найдено в available_levels), или None.
        """
        if not request:
            return None

        # Priority 1: direct match against available_levels (case-insensitive)
        if available_levels:
            text_lower = request.lower()
            for level_name in available_levels:
                if level_name.lower() in text_lower:
                    return level_name

        # Priority 2: regex patterns for level numbers
        patterns = [
            # "3 этаж", "2 уровень" and inflected forms ("3 этажа", "2 уровня", "2 этаже")
            (r'(\d+)\s*(?:этаж\w*|уровень?\w*)', 1),
            # "этаж 1", "уровень 3" and inflected forms ("этаже 2", "этажа 1")
            (r'(?:этаж\w*|уровень?\w*)\s*(\d+)', 1),
            # "Level 1", "Level 2"
            (r'[Ll]evel\s*(\d+)', 1),
        ]

        for pattern, group_idx in patterns:
            match = re.search(pattern, request, re.IGNORECASE | re.UNICODE)
            if match:
                return match.group(group_idx)

        return None

    def extract_target_parameter(self, request: str) -> Optional[str]:
        """
        Извлечь имя параметра из запроса.
        
        Ищет:
        - параметр "Марка" / параметр 'Марка'
        - "Марка" параметр
        - parameter "Mark"
        - [Марка] (слово в квадратных скобках)
        
        Returns:
            Имя параметра или None.
        """
        if not request:
            return None

        patterns = [
            # параметр "Mark" or параметра "Mark"
            r'параметр[ра]?\s+"([^"]+)"',
            r'параметр[ра]?\s+\'([^\']+)\'',
            # "Mark" параметр
            r'"([^"]+)"\s*параметр',
            # parameter "Mark"
            r'parameter\s+"([^"]+)"',
            r'parameter\s+\'([^\']+)\'',
            # [Марка] — слово в квадратных скобках
            r'\[([^\]]+)\]',
        ]

        for pattern in patterns:
            match = re.search(pattern, request, re.IGNORECASE | re.UNICODE)
            if match:
                return match.group(1).strip()

        return None
