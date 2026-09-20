"""CH098 - a class inherits from two or more bases that each declare a
non-empty ``__slots__``.

Verified directly:

    class A:
        __slots__ = ('a',)
    class B:
        __slots__ = ('b',)
    class C(A, B):
        __slots__ = ()
    # TypeError: multiple bases have instance lay-out conflict

Each non-empty `__slots__` reserves fixed-offset storage in the
instance's C-level memory layout - CPython can graft at most one such
layout onto a subclass, so inheriting from two classes that both
already have one is a layout Python cannot construct, full stop. This
raises the moment the class statement itself executes (import time),
regardless of whether the subclass is ever instantiated.

Only fires when 2+ of the class's own bases are themselves `ClassDef`s
defined earlier in the same file with a non-empty `__slots__` declared
directly in their own body - bases from other modules aren't visible to
a single-file AST check.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, literal_value


def _slot_count(cls: ast.ClassDef) -> int:
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__slots__"
        ):
            value = literal_value(stmt.value)
            if isinstance(value, tuple):
                return len(value)
            if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                return 1
            if isinstance(stmt.value, (ast.List, ast.Set)):
                return len(stmt.value.elts)
    return 0


class MultipleSlotsLayoutConflict(Check):
    code = "CH098"
    name = "multiple-slots-layout-conflict"
    description = "Inheriting from two bases that each declare a non-empty __slots__ raises TypeError at import time."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        classes_by_name = {
            node.name: node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
        }
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef) or len(cls.bases) < 2:
                continue
            slotted_bases = []
            for base in cls.bases:
                if not isinstance(base, ast.Name):
                    continue
                base_cls = classes_by_name.get(base.id)
                if base_cls is not None and _slot_count(base_cls) > 0:
                    slotted_bases.append(base.id)
            if len(slotted_bases) >= 2:
                findings.append(
                    Finding(
                        path=path,
                        line=cls.lineno,
                        col=cls.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}` inherits from {slotted_bases}, which each declare "
                            f"their own non-empty __slots__ - CPython can only graft one such "
                            f"instance layout per class, so this raises TypeError (multiple "
                            f"bases have instance lay-out conflict) at import time."
                        ),
                    )
                )
        return findings
