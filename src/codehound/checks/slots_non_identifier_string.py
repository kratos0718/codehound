"""CH103 - ``__slots__`` assigned a plain string that isn't itself a
single valid identifier.

Verified directly:

    class Foo:
        __slots__ = 'foo bar'
    # TypeError: __slots__ must be identifiers

    class Foo:
        __slots__ = 'foo,bar'
    # TypeError: __slots__ must be identifiers

A bare string assigned to `__slots__` is special-cased to mean *one*
slot named exactly that string, not a delimited list of names - unlike
`namedtuple`'s field-string convention, which does split on whitespace
and commas. Writing `__slots__ = 'foo bar'` expecting two slots (a
natural mistake if you've used `namedtuple("T", "foo bar")` before) gets
one slot literally named `"foo bar"`, and Python rejects that immediately
since it isn't a valid identifier. `__slots__ = 'foobar'` (no separator)
is genuinely fine - a single slot named `foobar` - and is never flagged.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class SlotsNonIdentifierString(Check):
    code = "CH103"
    name = "slots-non-identifier-string"
    description = "__slots__ assigned a string that isn't one valid identifier - raises TypeError at import time."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for stmt in cls.body:
                if not (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == "__slots__"
                ):
                    continue
                value = stmt.value
                if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                    continue
                if value.value.isidentifier():
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=stmt.lineno,
                        col=stmt.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}.__slots__` is the string {value.value!r}, which Python "
                            f"treats as one slot named exactly that (not a delimited list of "
                            f"names) - since it isn't a valid identifier, this raises TypeError: "
                            f"__slots__ must be identifiers, at import time."
                        ),
                    )
                )
        return findings
