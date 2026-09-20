"""CH067 - a ``typing.NamedTuple`` field with a mutable literal default is
shared by every instance that doesn't override it.

Verified directly: ``class Config(NamedTuple): tags: list = []`` then
``Config('a').tags is Config('b').tags`` is `True` - appending to one
instance's `tags` is visible through every other instance built without
its own `tags`. `NamedTuple` field defaults work exactly like an ordinary
function's default arguments (evaluated once, at class-definition time,
then reused), the same mechanism as CH002's mutable default argument -
*not* like a `pydantic.BaseModel` field default, which this project's own
FINDINGS.md documents as correctly copied per instance. The two look
identical at the type-annotation level; only the runtime behavior differs.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_namedtuple_base(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == "NamedTuple"
    return isinstance(base, ast.Attribute) and base.attr == "NamedTuple"


def _is_mutable_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set")


class NamedTupleMutableDefault(Check):
    code = "CH067"
    name = "namedtuple-mutable-default"
    description = "A typing.NamedTuple field's mutable literal default is shared by every instance, like a function's."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef) or not any(_is_namedtuple_base(b) for b in cls.bases):
                continue
            for stmt in cls.body:
                if (
                    isinstance(stmt, ast.AnnAssign)
                    and stmt.value is not None
                    and _is_mutable_literal(stmt.value)
                    and isinstance(stmt.target, ast.Name)
                ):
                    findings.append(
                        Finding(
                            path=path,
                            line=stmt.lineno,
                            col=stmt.col_offset,
                            code=self.code,
                            message=(
                                f"`{cls.name}.{stmt.target.id}`'s default is a mutable literal, "
                                f"shared by every instance that doesn't override it - NamedTuple "
                                f"field defaults work like an ordinary function's, evaluated "
                                f"once at class definition, not copied per instance."
                            ),
                        )
                    )
        return findings
