"""CH104 - a ``dataclasses.field(default=...)`` given a mutable literal
directly, instead of ``default_factory``.

Verified directly:

    from dataclasses import dataclass, field

    @dataclass
    class Foo:
        items: list = field(default=[])
    # ValueError: mutable default <class 'list'> for field items is not
    # allowed: use default_factory

Unlike a plain function's mutable default (silently shared, no error -
CH002), `dataclasses` actively checks each field's default for
hashability and refuses to build the class at all if it's mutable -
`field(default=[])`/`{}`/`set()` (or the equivalent literal/comprehension
forms) always hit this, since `list`/`dict`/`set` are all unhashable.
The fix is `field(default_factory=list)` (etc.), which calls the factory
fresh for every instance instead of sharing one object.

Only flags the unambiguous, always-unhashable literal forms - list/dict/
set literals and comprehensions, and bare `list()`/`dict()`/`set()`
calls. A default that's a call to some *other* name (e.g. a custom
class, or `collections.deque`, which is hashable and does not trigger
this) isn't flagged, since whether it actually crashes depends on that
type's own `__hash__`, which isn't visible from the AST alone.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_UNHASHABLE_FACTORIES = {"list", "dict", "set"}


def _is_unhashable_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.args and not node.keywords:
        return node.func.id in _UNHASHABLE_FACTORIES
    return False


def _is_field_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "field"
    if isinstance(func, ast.Attribute):
        return func.attr == "field"
    return False


class DataclassFieldMutableDefault(Check):
    code = "CH104"
    name = "dataclass-field-mutable-default"
    description = "dataclasses.field(default=<mutable literal>) - raises ValueError at class-creation time; use default_factory."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not _is_field_call(node):
                continue
            for kw in node.keywords:
                if kw.arg != "default":
                    continue
                if not _is_unhashable_literal(kw.value):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=kw.value.lineno,
                        col=kw.value.col_offset,
                        code=self.code,
                        message=(
                            "field(default=...) given a mutable list/dict/set literal - "
                            "raises ValueError ('mutable default ... is not allowed: use "
                            "default_factory') the moment the dataclass is defined. Use "
                            "default_factory=list/dict/set (or a lambda) instead."
                        ),
                    )
                )
        return findings
