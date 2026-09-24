"""CH101 - a ``@x.setter``/``@x.deleter`` decorator where ``x`` was never
established as a property earlier in the same class body.

Verified directly:

    class Foo:
        @x.setter
        def x(self, value):
            self._x = value
    # NameError: name 'x' is not defined

A class body executes top to bottom in its own namespace; `@x.setter`
needs `x` to already be bound there - to the `property` object created by
an earlier `@property def x(self): ...` in the *same* class - before this
line runs. Getting the order wrong (setter before getter), or a typo in
the name, leaves `x` unbound. Inheriting a same-named property from a
base class does not help either: the class body's own namespace has no
access to base-class attributes as bare names while it's still executing,
so the lookup fails the same way. Verified: swapping the property/setter
order, or defining the property in a base class instead, both still raise
the identical `NameError`.

Only fires when the name is never bound by anything - a `@property`, a
plain assignment, or an earlier `@name.setter`/`@name.deleter` (the
correct chained form) - earlier in the same class body. A name introduced
any other way (e.g. a `for` loop, an import) is intentionally not
distinguished from "not a property yet" - being bound to something that
isn't a property fails at the same line too, just with a different
exception, so treating it as a hit rather than staying silent is the
safer default.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_ACCESSOR_ATTRS = {"setter", "deleter", "getter"}


def _bound_names_before(cls: ast.ClassDef, index: int) -> set[str]:
    bound: set[str] = set()
    for stmt in cls.body[:index]:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    bound.add(target.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            bound.add(stmt.target.id)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(stmt.name)
    return bound


def _accessor_target(deco: ast.expr) -> str | None:
    if isinstance(deco, ast.Attribute) and deco.attr in _ACCESSOR_ATTRS and isinstance(deco.value, ast.Name):
        return deco.value.id
    return None


class SetterBeforeProperty(Check):
    code = "CH101"
    name = "setter-before-property"
    description = "@x.setter/@x.deleter where x was never bound as a property earlier in the class - raises NameError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for index, stmt in enumerate(cls.body):
                if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for deco in stmt.decorator_list:
                    target = _accessor_target(deco)
                    if target is None:
                        continue
                    if target in _bound_names_before(cls, index):
                        continue
                    findings.append(
                        Finding(
                            path=path,
                            line=deco.lineno,
                            col=deco.col_offset,
                            code=self.code,
                            message=(
                                f"`@{target}.{deco.attr}` on `{cls.name}.{stmt.name}` runs before "
                                f"`{target}` is bound to anything in this class - raises NameError: "
                                f"name '{target}' is not defined. A `@property def {target}` must "
                                f"come first in the class body (inheriting one from a base class "
                                f"does not help)."
                            ),
                        )
                    )
        return findings
