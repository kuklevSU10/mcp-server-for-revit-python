# -*- coding: utf-8 -*-
"""Demo: _semantic_match_vor_to_bim keyword fallback"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from custom_tools import vor_vs_bim as mod
from custom_tools.vor_vs_bim import _semantic_match_vor_to_bim

mod._SEMANTIC_CACHE.clear()

bim_categories = [
    "Kirpichnaya kladka naruzhnyh sten",
    "Monolitnye zh/b konstruktsii",
    "Krovlya iz profnastila",
    "Okonnye bloki",
    "Vnutrennie peregorodki",
    "Fundamentnaya plita",
]

# Cyrillics via unicode escapes for subprocess safety
test_cases = [
    ("\u041a\u043b\u0430\u0434\u043a\u0430 \u043a\u0438\u0440\u043f\u0438\u0447\u043d\u0430\u044f \u043d\u0430\u0440\u0443\u0436\u043d\u0430\u044f \u0442\u043e\u043b\u0449. 510\u043c\u043c",
     "Kirpichnaya kladka naruzhnyh sten"),  # should match kladka
    ("\u041f\u043b\u0438\u0442\u0430 \u0444\u0443\u043d\u0434\u0430\u043c\u0435\u043d\u0442\u043d\u0430\u044f \u043c\u043e\u043d\u043e\u043b\u0438\u0442\u043d\u0430\u044f",
     "Fundamentnaya plita"),  # should match fundamentnaya
    ("\u041f\u0435\u0440\u0435\u0433\u043e\u0440\u043e\u0434\u043a\u0430 \u043f\u043e\u043a\u043e\u043c\u043d\u0430\u0442\u043d\u0430\u044f",
     "Vnutrennie peregorodki"),  # should match peregorodki
]

print("=== _semantic_match_vor_to_bim DEMO (keyword fallback mode) ===\n", flush=True)
passed = 0
for vor_name, expected in test_cases:
    result = _semantic_match_vor_to_bim(vor_name, bim_categories)
    ok = "[PASS]" if result == expected else "[INFO]"
    if result == expected:
        passed += 1
    print("{} vor='{}' -> '{}'".format(ok, vor_name[:30], result), flush=True)

print("\n{}/{} correct matches".format(passed, len(test_cases)), flush=True)
print("\nCache size: {} entries".format(len(mod._SEMANTIC_CACHE)), flush=True)

# Show tolerance_pct in docstring
import inspect
from custom_tools.vor_vs_bim import register_vor_vs_bim_tools
src = inspect.getsource(register_vor_vs_bim_tools)
idx = src.find("tolerance_pct: acceptable deviation")
if idx >= 0:
    print("\n[OK] Docstring: " + src[idx:idx+60].strip(), flush=True)
