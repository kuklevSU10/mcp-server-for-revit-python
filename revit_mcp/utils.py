# -*- coding: utf-8 -*-
from pyrevit import DB
import traceback
import logging

logger = logging.getLogger(__name__)


def normalize_string(text):
    """Safely normalize string values, always returning a unicode string.

    In IronPython 2, calling str() on a .NET System.String that contains
    non-ASCII characters (e.g. accented letters) produces a byte string
    encoded with the system default codec.  The pyRevit Routes JSON encoder
    then fails with 'unknown codec can't decode byte 0xNN'.

    By returning unicode we guarantee the JSON serialiser receives a proper
    text object regardless of the locale of the Revit model.
    """
    if text is None:
        return u"Unnamed"
    # Already a unicode string (normal case for .NET System.String in IronPython)
    if isinstance(text, unicode):
        return text.strip()
    # Byte string — decode with a permissive fallback
    if isinstance(text, str):
        try:
            return text.decode("utf-8").strip()
        except (UnicodeDecodeError, AttributeError):
            return text.decode("latin-1").strip()
    # Any other type (.NET object, int, etc.) — convert via unicode()
    try:
        return unicode(text).strip()
    except Exception:
        return u"Unnamed"


def get_element_name(element):
    """
    Get the name of a Revit element.
    Tries multiple approaches for maximum IronPython 2 compatibility.
    """
    # Attempt 1: direct .Name property (works for most element types)
    try:
        n = element.Name
        if n is not None:
            return n
    except Exception:
        pass
    # Attempt 2: VIEW_NAME parameter (works for View subclasses)
    try:
        p = element.get_Parameter(DB.BuiltInParameter.VIEW_NAME)
        if p and p.HasValue:
            v = p.AsString()
            if v:
                return v
    except Exception:
        pass
    # Attempt 3: DB.Element.Name descriptor
    try:
        return DB.Element.Name.__get__(element)
    except Exception:
        pass
    # Attempt 4: SYMBOL_NAME_PARAM (for ElementType subclasses)
    try:
        p = element.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p and p.HasValue:
            return p.AsString()
    except Exception:
        pass
    return u"Unknown"


def find_family_symbol_safely(doc, target_family_name, target_type_name=None):
    """
    Safely find a family symbol by name
    """
    try:
        collector = DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)

        for symbol in collector:
            if symbol.Family.Name == target_family_name:
                if not target_type_name or symbol.Name == target_type_name:
                    return symbol
        return None
    except Exception as e:
        logger.error("Error finding family symbol: %s", str(e))
        return None
