"""CH062 - a class decorated with ``@functools.total_ordering`` doesn't
define its own ``__eq__``.

``total_ordering`` fills in the missing comparison methods (``__le__``,
``__gt__``, ``__ge__``) from whichever *one* ordering method you supply,
using the class's ``__eq__`` to do it. Verified directly: a class that
defines only ``__lt__`` and skips ``__eq__`` silently falls back to
``object``'s identity-based ``__eq__`` - two instances with the exact same
data compare unequal (``a == b`` is `False` for `Money(10) == Money(10)`),
and every method `total_ordering` derived from it inherits that wrong
answer (`a <= b` is also `False` for equal values). Nothing raises
anywhere; the class works, just not correctly, and the incorrect results
degrade silently - sorting still "works", equality checks are just wrong.

Only fires when the class body has no ``__eq__`` of its own - inheriting
one from a base class (not `object`'s default) is not flagged, since that
usually *is* the intended, correct `__eq__`.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_total_ordering_decorator(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Name):
        return dec.id == "total_ordering"
    if isinstance(dec, ast.Attribute):
        return dec.attr == "total_ordering"
    return False


def _defines_eq(cls: ast.ClassDef) -> bool:
    return any(isinstance(stmt, ast.FunctionDef) and stmt.name == "__eq__" for stmt in cls.body)


_ORDERING_METHODS = {"__lt__", "__le__", "__gt__", "__ge__"}


def _orders_by_identity(cls: ast.ClassDef) -> bool:
    """An ordering method comparing `id(...)` values.

    If ordering is identity-based on purpose, the default identity `__eq__`
    is exactly consistent with it - kombu's timer `Entry.__lt__` is
    `id(self) < id(other)` ("must not use hash() to order entries").
    """
    for stmt in cls.body:
        if not isinstance(stmt, ast.FunctionDef) or stmt.name not in _ORDERING_METHODS:
            continue
        for node in ast.walk(stmt):
            if isinstance(node, ast.Compare):
                operands = [node.left, *node.comparators]
                if all(
                    isinstance(o, ast.Call) and isinstance(o.func, ast.Name) and o.func.id == "id"
                    for o in operands
                ):
                    return True
    return False


def _has_custom_base(cls: ast.ClassDef) -> bool:
    return not (not cls.bases or (len(cls.bases) == 1 and isinstance(cls.bases[0], ast.Name) and cls.bases[0].id == "object"))


class TotalOrderingMissingEq(Check):
    code = "CH062"
    name = "total-ordering-missing-eq"
    description = "@total_ordering needs its own __eq__ to derive correct comparisons; the class has none."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            deco = next((d for d in cls.decorator_list if _is_total_ordering_decorator(d)), None)
            if deco is None:
                continue
            if _has_custom_base(cls):
                continue  # a base class may already provide a correct __eq__
            if _defines_eq(cls):
                continue
            if _orders_by_identity(cls):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=deco.lineno,
                    col=deco.col_offset,
                    code=self.code,
                    message=(
                        f"`{cls.name}` is decorated with @total_ordering but defines no "
                        f"`__eq__` of its own - it falls back to identity-based equality, "
                        f"so two instances with equal data compare unequal, and every "
                        f"comparison method derived from that is wrong too."
                    ),
                )
            )
        return findings
