"""CH102 - a class decorated with ``@functools.total_ordering`` defines
none of ``__lt__``/``__le__``/``__gt__``/``__ge__``.

Verified directly:

    import functools

    @functools.total_ordering
    class Foo:
        def __eq__(self, other):
            return True
    # ValueError: must define at least one ordering operation: < > <= >=

`total_ordering` fills in the other three comparison methods from
whichever *one* you supply - it needs that one to derive the rest from.
Defining `__eq__` alone (a common mistake: `__eq__` reads like "the"
comparison method to provide) is not enough, and `functools` itself
raises `ValueError` at class-decoration time, before the class is even
usable - this is a distinct failure from CH062 (`@total_ordering` with no
`__eq__`, which degrades silently instead of raising).

Only fires when the class body defines none of the four ordering dunders
itself; inheriting one from a base class satisfies `total_ordering`'s
requirement (it looks the method up on the class, not just `__dict__`),
so that case is not flagged.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_ORDERING_DUNDERS = {"__lt__", "__le__", "__gt__", "__ge__"}


def _is_total_ordering_decorator(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Name):
        return dec.id == "total_ordering"
    if isinstance(dec, ast.Attribute):
        return dec.attr == "total_ordering"
    return False


def _has_custom_base(cls: ast.ClassDef) -> bool:
    return not (
        not cls.bases or (len(cls.bases) == 1 and isinstance(cls.bases[0], ast.Name) and cls.bases[0].id == "object")
    )


class TotalOrderingNoMethods(Check):
    code = "CH102"
    name = "total-ordering-no-methods"
    description = "@total_ordering with none of __lt__/__le__/__gt__/__ge__ defined - raises ValueError at import time."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            deco = next((d for d in cls.decorator_list if _is_total_ordering_decorator(d)), None)
            if deco is None:
                continue
            if _has_custom_base(cls):
                continue  # a base class may supply one of the four
            own_methods = {stmt.name for stmt in cls.body if isinstance(stmt, ast.FunctionDef)}
            if own_methods & _ORDERING_DUNDERS:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=deco.lineno,
                    col=deco.col_offset,
                    code=self.code,
                    message=(
                        f"`{cls.name}` is decorated with @total_ordering but defines none of "
                        f"__lt__/__le__/__gt__/__ge__ - raises ValueError ('must define at "
                        f"least one ordering operation') at class-decoration time."
                    ),
                )
            )
        return findings
