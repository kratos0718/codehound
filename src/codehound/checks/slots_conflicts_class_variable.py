"""CH081 - a name in ``__slots__`` also has a class-level value assignment.

Verified directly:

    class S:
        __slots__ = ('x',)
        x = 5
    # ValueError: 'x' in __slots__ conflicts with class variable

`__slots__` reserves a descriptor-backed storage slot for each name; a
plain class-level assignment to that same name tries to bind a class
attribute over that descriptor, and Python refuses outright the moment
the class body finishes executing (import time). A bare annotation with
no value (`x: int` alongside `__slots__ = ('x',)`) is the correct,
standard pairing and is never flagged - the conflict only exists when the
name is actually assigned a class-level value.

Only fires on a class with no custom `metaclass=`. Found for real in
pydantic's own `BaseModel`: it declares `__slots__` containing
`__pydantic_extra__` and also gives that name a class-level value
(`= NoInitField(...)`), which would conflict under plain `type` - but
`BaseModel` is built with `metaclass=ModelMetaclass`, which rewrites the
class namespace before `type.__new__` ever sees it, sidestepping the
conflict entirely. A custom metaclass can do this for any class, so
there's no way to tell from the AST alone whether the conflict is real.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, literal_value, UNRESOLVED


def _slot_names(value: ast.expr) -> list[str]:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        return [value.value]
    if isinstance(value, (ast.Tuple, ast.List, ast.Set)):
        names = []
        for elt in value.elts:
            v = literal_value(elt)
            if isinstance(v, str):
                names.append(v)
        return names
    return []


def _has_custom_metaclass(cls: ast.ClassDef) -> bool:
    for kw in cls.keywords:
        if kw.arg == "metaclass":
            return True
    return False


class SlotsConflictsClassVariable(Check):
    code = "CH081"
    name = "slots-conflicts-class-variable"
    description = "A name in __slots__ also has a class-level value assignment - raises ValueError at import time."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if _has_custom_metaclass(cls):
                continue
            slots: set[str] = set()
            for stmt in cls.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == "__slots__"
                ):
                    slots.update(_slot_names(stmt.value))
            if not slots:
                continue
            for stmt in cls.body:
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name) and target.id in slots and target.id != "__slots__":
                            findings.append(
                                Finding(
                                    path=path,
                                    line=stmt.lineno,
                                    col=stmt.col_offset,
                                    code=self.code,
                                    message=(
                                        f"`{cls.name}.{target.id}` is both in __slots__ and "
                                        f"assigned a class-level value - raises ValueError "
                                        f"('{target.id}' in __slots__ conflicts with class "
                                        f"variable) at import time."
                                    ),
                                )
                            )
                elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                    if isinstance(stmt.target, ast.Name) and stmt.target.id in slots:
                        findings.append(
                            Finding(
                                path=path,
                                line=stmt.lineno,
                                col=stmt.col_offset,
                                code=self.code,
                                message=(
                                    f"`{cls.name}.{stmt.target.id}` is both in __slots__ and "
                                    f"assigned a class-level value - raises ValueError "
                                    f"('{stmt.target.id}' in __slots__ conflicts with class "
                                    f"variable) at import time."
                                ),
                            )
                        )
        return findings
