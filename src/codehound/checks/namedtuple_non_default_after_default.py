"""CH080 - a ``typing.NamedTuple`` field with no default is declared after
one that has a default.

Verified directly:

    class NT(NamedTuple):
        x: int = 0
        y: int
    # TypeError: Non-default namedtuple field y cannot follow default field x

Same underlying constraint as a dataclass's field order (CH079), applied
by `NamedTupleMeta` instead of the `@dataclass` decorator - the generated
`__new__` needs every defaulted parameter to come after every required
one, and `NamedTuple` builds that parameter list directly from class-body
order. This raises the moment the class statement executes (import time).
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _inherits_namedtuple(cls: ast.ClassDef) -> bool:
    for base in cls.bases:
        if isinstance(base, ast.Name) and base.id == "NamedTuple":
            return True
        if isinstance(base, ast.Attribute) and base.attr == "NamedTuple":
            return True
    return False


class NamedTupleNonDefaultAfterDefault(Check):
    code = "CH080"
    name = "namedtuple-non-default-after-default"
    description = "A NamedTuple field with no default follows one that has a default - raises TypeError at import time."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef) or not _inherits_namedtuple(cls):
                continue
            seen_default: ast.AnnAssign | None = None
            for stmt in cls.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                if stmt.value is None:
                    if seen_default is not None:
                        findings.append(
                            Finding(
                                path=path,
                                line=stmt.lineno,
                                col=stmt.col_offset,
                                code=self.code,
                                message=(
                                    f"`{cls.name}.{stmt.target.id}` has no default and follows "
                                    f"`{seen_default.target.id}`, which does - NamedTuple builds "
                                    f"__new__ in field order, and a required field can't follow "
                                    f"a defaulted one. Raises TypeError at import time."
                                ),
                            )
                        )
                else:
                    seen_default = stmt
        return findings
