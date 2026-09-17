"""CH015 - ``@property`` on an ``async def`` method returns an unawaited coroutine.

Accessing a property never uses ``await`` - ``obj.thing`` is a plain
attribute access, so Python has no way to know it should await anything
even if the getter is a coroutine function. ``@property async def thing`` is
syntactically legal, but every access silently hands back a coroutine
object instead of the value, which is truthy, doesn't equal what you
compare it to, and (if never awaited) is a hidden
``RuntimeWarning: coroutine 'thing' was never awaited`` waiting to happen
the first time someone actually uses the ``@property`` the way properties
are meant to be used.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_property_decorator(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Name):
        return dec.id == "property"
    if isinstance(dec, ast.Attribute):
        return dec.attr in ("property", "cached_property")
    return False


class AsyncProperty(Check):
    code = "CH015"
    name = "async-property"
    description = "@property wrapping an async def returns an unawaited coroutine, not the value."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(_is_property_decorator(d) for d in node.decorator_list):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{node.name}` is an `async def` wrapped in `@property` - accessing it "
                        f"never awaits anything, so every access returns an unawaited coroutine "
                        f"object, not the value."
                    ),
                )
            )
        return findings
