"""CH059 - a decorator factory builds a ``@functools.wraps``-wrapped inner
function, then never mentions it again anywhere else in the same function.

``@functools.wraps(func)`` on a nested function is an almost unambiguous
signal that the outer function is a decorator, and that the inner function
is the replacement it's supposed to install somewhere - most often via
``return wrapper``, but real code was found installing it several other
ways too: a conditional expression choosing between a sync/async pair
(``return async_wrapper if ... else wrapper``, llama_index's own tracing
decorator), reassigning it to another local name before returning that
(agno's ``wrapper = async_wrapper if ... else sync_wrapper``), attaching it
directly (``cls.__init__ = wrapper``, transformers' dataclass-kwargs
patcher), or handing it to ``setattr(...)``. Trying to enumerate every
installation shape individually turned out to be exactly the wrong bar -
each corpus pass surfaced one more legitimate one. The bar this settled on
instead: is the inner function's name referenced *anywhere else at all* in
the outer function's body? If a name built with @wraps is never mentioned
again by name anywhere - not returned, not reassigned, not attached to
anything - there is no reading where that isn't simply forgotten, since
verified directly, whatever the outer function *does* return instead
(``None``, with no other return) turns the "decorated" name into something
that raises ``TypeError: 'NoneType' object is not callable`` at every call
site, nowhere near the missing wiring.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_wraps_decorator(dec: ast.expr) -> bool:
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id == "wraps"
    if isinstance(target, ast.Attribute):
        return target.attr == "wraps"
    return False


def _find_wrapped_inners(outer: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        stmt
        for stmt in outer.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_wraps_decorator(dec) for dec in stmt.decorator_list)
    ]


def _is_referenced_elsewhere(outer: ast.FunctionDef | ast.AsyncFunctionDef, inner: ast.stmt, name: str) -> bool:
    """Is `name` mentioned anywhere in `outer` other than inside `inner`'s
    own body? A *sibling* @wraps-decorated helper calling this one still
    counts - found for real in dspy, where a `process_request` helper is
    also decorated with @wraps and is only ever called from the actual
    sync/async wrapper functions, not returned itself."""
    for stmt in outer.body:
        if stmt is inner:
            continue
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and node.id == name:
                return True
    return False


class DecoratorMissingReturn(Check):
    code = "CH059"
    name = "decorator-missing-return"
    description = "A @functools.wraps-wrapped inner function is never referenced again anywhere in its own function."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for outer in ast.walk(tree):
            if not isinstance(outer, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            inners = _find_wrapped_inners(outer)
            if not inners:
                continue
            for inner in inners:
                if _is_referenced_elsewhere(outer, inner, inner.name):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=inner.lineno,
                        col=inner.col_offset,
                        code=self.code,
                        message=(
                            f"`{outer.name}` builds `{inner.name}` with @wraps, marking it as "
                            f"the function meant to replace whatever `{outer.name}` decorates, "
                            f"but `{inner.name}` is never mentioned again anywhere in "
                            f"`{outer.name}` - not returned, not assigned anywhere."
                        ),
                    )
                )
        return findings
