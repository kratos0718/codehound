"""CH026 - mutable class attribute mutated in place, never given a per-instance copy.

`class C: items = []` creates *one* list, owned by the class itself, at
class-definition time - not one per instance. `self.items` reads it
through the normal attribute lookup fallback (instance dict, then class
dict), which works fine for reading. The trap is writing to it *in
place* - `self.items.append(x)` doesn't create an instance attribute,
it mutates the single shared list every instance still points at, so
one instance's append shows up in every other instance's `items` too.
The class-level mutable default silently becomes global-ish state, the
same failure mode as CH002's mutable default argument, one scope up.

Only fires when `__init__` (or any other method) never does `self.items
= ...` anywhere in the class - that reassignment would correctly shadow
the class attribute with a fresh per-instance one from then on, which is
the standard fix and a common enough pattern that this check treats its
mere presence as proof the class already handles it right.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_MUTATING_METHODS = {"append", "extend", "update", "add", "insert", "remove", "pop", "clear", "discard"}


def _is_mutable_literal_or_factory(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set"):
        return not node.args and not node.keywords
    return False


def _class_level_mutable_attrs(cls: ast.ClassDef) -> dict[str, ast.Assign]:
    out: dict[str, ast.Assign] = {}
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and _is_mutable_literal_or_factory(stmt.value)
        ):
            out[stmt.targets[0].id] = stmt
    return out


def _is_self_attr(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == name and isinstance(node.value, ast.Name) and node.value.id == "self"


def _is_reassigned_on_self(cls: ast.ClassDef, name: str) -> bool:
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if _is_self_attr(tgt, name):
                    return True
        if isinstance(node, ast.AugAssign) and _is_self_attr(node.target, name):
            return True
    return False


def _is_mutated_in_place_on_self(cls: ast.ClassDef, name: str) -> bool:
    for node in ast.walk(cls):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
            and _is_self_attr(node.func.value, name)
        ):
            return True
        if isinstance(node, ast.Subscript) and _is_self_attr(node.value, name) and isinstance(node.ctx, ast.Store):
            return True
    return False


class MutableClassAttribute(Check):
    code = "CH026"
    name = "mutable-class-attribute"
    description = "Class-level mutable default (list/dict/set) mutated in place is shared by every instance."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for name, stmt in _class_level_mutable_attrs(cls).items():
                if _is_reassigned_on_self(cls, name):
                    continue
                if not _is_mutated_in_place_on_self(cls, name):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=stmt.lineno,
                        col=stmt.col_offset,
                        code=self.code,
                        message=(
                            f"`{name}` is a class-level mutable default on `{cls.name}`, mutated "
                            f"in place via `self.{name}` without ever being reassigned per "
                            f"instance - every instance shares and mutates the same object. Set "
                            f"`self.{name} = ...` in `__init__` to give each instance its own."
                        ),
                    )
                )
        return findings
