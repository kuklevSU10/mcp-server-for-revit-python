# -*- coding: utf-8 -*-
"""Input validation helpers for BIM MCP tools."""


def validate_filters(filters):
    """Validate bim_search filters list."""
    if not isinstance(filters, list):
        return "filters must be a list"
    for i, f in enumerate(filters):
        if not isinstance(f, dict):
            return "filter[{}] must be a dict".format(i)
        if 'param' not in f:
            return "filter[{}] missing 'param' key".format(i)
        if 'op' not in f:
            return "filter[{}] missing 'op' key".format(i)
        valid_ops = [
            'contains', 'not_contains', 'eq', 'neq',
            'gt', 'lt', 'gte', 'lte',
            'is_empty', 'not_empty', 'starts_with',
        ]
        if f['op'] not in valid_ops:
            return "filter[{}] invalid op '{}'. Valid: {}".format(i, f['op'], valid_ops)
    return None  # OK


def validate_element_id(element_id):
    """Validate Revit element ID."""
    if not isinstance(element_id, int) or element_id <= 0:
        return "element_id must be a positive integer"
    return None


def validate_vor_data(vor_data_str):
    """Validate VOR JSON data."""
    import json
    try:
        items = json.loads(vor_data_str)
    except Exception as e:
        return "Invalid JSON: " + str(e)
    if not isinstance(items, list):
        return "vor_data must be a JSON array"
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return "item[{}] must be a dict".format(i)
        if 'name' not in item:
            return "item[{}] missing 'name'".format(i)
    return None
