"""
H5 Tests — Intent Classifier V2

Tests for extract_target_category(), extract_target_level(),
extract_target_parameter(), and updated classify() with hints.
"""

import pytest
from revit_mcp.execute_v2.intent_classifier import IntentClassifier


@pytest.fixture
def clf():
    return IntentClassifier()


# ---------------------------------------------------------------------------
# extract_target_category
# ---------------------------------------------------------------------------

def test_extract_category_walls_ru(clf):
    """'найди все стены' → 'OST_Walls'"""
    assert clf.extract_target_category("найди все стены") == "OST_Walls"


def test_extract_category_doors_ru(clf):
    """'список дверей' → 'OST_Doors'"""
    assert clf.extract_target_category("список дверей") == "OST_Doors"


def test_extract_category_windows_en(clf):
    """'list windows' → 'OST_Windows'"""
    assert clf.extract_target_category("list windows") == "OST_Windows"


def test_extract_category_rooms_ru(clf):
    """'помещения на этаже' → 'OST_Rooms'"""
    assert clf.extract_target_category("помещения на этаже") == "OST_Rooms"


def test_extract_category_floors_ru(clf):
    """'площадь перекрытий' → 'OST_Floors'"""
    assert clf.extract_target_category("площадь перекрытий") == "OST_Floors"


def test_extract_category_none(clf):
    """'привет' → None"""
    assert clf.extract_target_category("привет") is None


def test_extract_category_doors_en(clf):
    """'count all doors on level 1' → 'OST_Doors'"""
    assert clf.extract_target_category("count all doors on level 1") == "OST_Doors"


def test_extract_category_furniture_ru(clf):
    """'мебель в офисе' → 'OST_Furniture'"""
    assert clf.extract_target_category("мебель в офисе") == "OST_Furniture"


def test_extract_category_beams_en(clf):
    """'list all beams' → 'OST_StructuralFraming'"""
    assert clf.extract_target_category("list all beams") == "OST_StructuralFraming"


def test_extract_category_stairs_ru(clf):
    """'лестница на 2 этаже' → 'OST_Stairs'"""
    assert clf.extract_target_category("лестница на 2 этаже") == "OST_Stairs"


# ---------------------------------------------------------------------------
# extract_target_level
# ---------------------------------------------------------------------------

def test_extract_level_digit_before_ru(clf):
    """'3 этаж' → '3'"""
    assert clf.extract_target_level("3 этаж") == "3"


def test_extract_level_digit_after_ru(clf):
    """'этаж 1' → '1'"""
    assert clf.extract_target_level("этаж 1") == "1"


def test_extract_level_en(clf):
    """'Level 2' → '2'"""
    assert clf.extract_target_level("Level 2") == "2"


def test_extract_level_from_available(clf):
    """'покажи Уровень 1' with available_levels → 'Уровень 1'"""
    result = clf.extract_target_level(
        "покажи Уровень 1",
        available_levels=["Уровень 1", "Уровень 2"],
    )
    assert result == "Уровень 1"


def test_extract_level_none(clf):
    """'найди все двери' → None"""
    assert clf.extract_target_level("найди все двери") is None


def test_extract_level_уровень_number(clf):
    """'уровень 3' → '3'"""
    assert clf.extract_target_level("уровень 3") == "3"


def test_extract_level_level_case_insensitive(clf):
    """'level 5' → '5' (lowercase)"""
    assert clf.extract_target_level("level 5") == "5"


# ---------------------------------------------------------------------------
# extract_target_parameter
# ---------------------------------------------------------------------------

def test_extract_parameter_quotes(clf):
    """'параметр "Mark"' → 'Mark'"""
    assert clf.extract_target_parameter('параметр "Mark"') == "Mark"


def test_extract_parameter_brackets(clf):
    """'заполни [Марка] у всех стен' → 'Марка'"""
    assert clf.extract_target_parameter("заполни [Марка] у всех стен") == "Марка"


def test_extract_parameter_none(clf):
    """'найди все двери' → None"""
    assert clf.extract_target_parameter("найди все двери") is None


def test_extract_parameter_single_quotes(clf):
    """'параметра 'Марка'' → 'Марка'"""
    assert clf.extract_target_parameter("параметра 'Марка'") == "Марка"


def test_extract_parameter_en_keyword(clf):
    """'parameter "Description"' → 'Description'"""
    assert clf.extract_target_parameter('parameter "Description"') == "Description"


def test_extract_parameter_before_keyword(clf):
    """'"Марка" параметр у дверей' → 'Марка'"""
    assert clf.extract_target_parameter('"Марка" параметр у дверей') == "Марка"


# ---------------------------------------------------------------------------
# classify() — hints integration
# ---------------------------------------------------------------------------

def test_hints_in_classify_result(clf):
    """classify() ALWAYS returns 'hints' key."""
    result = clf.classify("привет")
    assert "hints" in result
    assert "target_category" in result["hints"]
    assert "target_level" in result["hints"]
    assert "target_parameter" in result["hints"]


def test_classify_with_hints(clf):
    """Full classify() returns populated hints for rich request."""
    result = clf.classify('найди все двери на этаже 2 и заполни параметр "Марка"')
    assert result["hints"]["target_category"] == "OST_Doors"
    assert result["hints"]["target_level"] == "2"
    assert result["hints"]["target_parameter"] == "Марка"


def test_classify_hints_none_for_empty(clf):
    """Empty request → all hints are None."""
    result = clf.classify("")
    assert result["hints"]["target_category"] is None
    assert result["hints"]["target_level"] is None
    assert result["hints"]["target_parameter"] is None


def test_classify_backward_compat(clf):
    """classify() still returns intent_type, confidence, detected_keywords."""
    result = clf.classify("найди все стены")
    assert "intent_type" in result
    assert "confidence" in result
    assert "detected_keywords" in result


def test_classify_category_only(clf):
    """Request with only category hint."""
    result = clf.classify("список окон")
    assert result["hints"]["target_category"] == "OST_Windows"
    assert result["hints"]["target_level"] is None
    assert result["hints"]["target_parameter"] is None
