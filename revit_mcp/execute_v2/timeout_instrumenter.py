"""
Timeout Instrumenter — injects loop iteration counters into IronPython code.

Protects against infinite loops since IronPython doesn't support threading.Timer properly.
Uses AST transformation on Python 3 side, outputs IronPython 2.7 compatible code.
"""

import ast
import hashlib
import textwrap
import threading
from typing import Optional

# AST caching to speed up identical requests
_instrument_cache = {}
_cache_lock = threading.Lock()
_CACHE_MAX_SIZE = 200

# Counter variable prefix (unlikely to collide with user code)
_COUNTER_PREFIX = "_kukai_loop_cnt_"
_local = threading.local()


def _next_counter_name() -> str:
    """Generate a unique counter variable name (thread-safe)."""
    if not hasattr(_local, 'counter_id'):
        _local.counter_id = 0
    _local.counter_id += 1
    return "{}{}".format(_COUNTER_PREFIX, _local.counter_id)


def reset_counter():
    """Reset the thread-local counter (useful for testing)."""
    if hasattr(_local, 'counter_id'):
        _local.counter_id = 0


class _LoopInstrumenter(ast.NodeTransformer):
    """AST transformer that injects iteration counters into for/while loops."""

    def __init__(self, max_iterations: int):
        self.max_iterations = max_iterations

    def _make_guard(self, counter_name: str) -> ast.AST:
        """
        Create AST nodes for:
            _kukai_loop_cnt_N += 1
            if _kukai_loop_cnt_N > max_iterations:
                raise RuntimeError("KUKAI: Loop limit exceeded (...)")
        """
        # counter += 1
        increment = ast.AugAssign(
            target=ast.Name(id=counter_name, ctx=ast.Store()),
            op=ast.Add(),
            value=ast.Constant(value=1),
        )

        # raise RuntimeError(...)
        error_msg = "KUKAI: Loop limit exceeded ({} iterations)".format(
            self.max_iterations
        )
        raise_stmt = ast.Raise(
            exc=ast.Call(
                func=ast.Name(id="RuntimeError", ctx=ast.Load()),
                args=[ast.Constant(value=error_msg)],
                keywords=[],
            ),
            cause=None,
        )

        # if counter > max_iterations: raise ...
        check = ast.If(
            test=ast.Compare(
                left=ast.Name(id=counter_name, ctx=ast.Load()),
                ops=[ast.Gt()],
                comparators=[ast.Constant(value=self.max_iterations)],
            ),
            body=[raise_stmt],
            orelse=[],
        )

        return increment, check

    def _make_init(self, counter_name: str) -> ast.AST:
        """Create: _kukai_loop_cnt_N = 0"""
        return ast.Assign(
            targets=[ast.Name(id=counter_name, ctx=ast.Store())],
            value=ast.Constant(value=0),
        )

    def visit_For(self, node: ast.For) -> ast.AST:
        """Instrument for loops."""
        self.generic_visit(node)  # recurse into nested loops first
        counter_name = _next_counter_name()
        increment, check = self._make_guard(counter_name)

        # Prepend guard to loop body
        node.body = [increment, check] + node.body

        # Wrap: init counter, then loop
        init = self._make_init(counter_name)
        return [init, node]

    def visit_While(self, node: ast.While) -> ast.AST:
        """Instrument while loops."""
        self.generic_visit(node)  # recurse into nested loops first
        counter_name = _next_counter_name()
        increment, check = self._make_guard(counter_name)

        # Prepend guard to loop body
        node.body = [increment, check] + node.body

        # Wrap: init counter, then loop
        init = self._make_init(counter_name)
        return [init, node]


def instrument_loops(code: str, max_iterations: int = 100_000) -> str:
    """
    Instrument all for/while loops in IronPython code with iteration counters.

    Args:
        code: Source code string (IronPython 2.7 compatible)
        max_iterations: Maximum allowed iterations per loop (default 100K)

    Returns:
        Instrumented code string with loop guards inserted.

    Raises:
        SyntaxError: If the code cannot be parsed.
    """
    # Check cache first
    cache_key = hashlib.sha256(code.encode("utf-8")).hexdigest()
    with _cache_lock:
        if cache_key in _instrument_cache:
            return _instrument_cache[cache_key]

    reset_counter()

    tree = ast.parse(code)
    transformer = _LoopInstrumenter(max_iterations)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)

    result = ast.unparse(new_tree)
    
    with _cache_lock:
        if len(_instrument_cache) >= _CACHE_MAX_SIZE:
            # Simple eviction - clear half the cache
            keys = list(_instrument_cache.keys())
            for k in keys[:_CACHE_MAX_SIZE // 2]:
                del _instrument_cache[k]
        _instrument_cache[cache_key] = result
        
    return result
