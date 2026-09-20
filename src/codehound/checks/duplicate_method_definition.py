"""CH076 - the same method name is defined twice, directly, in one class
body.

Verified directly:

    class Foo:
        def bar(self): return 1
        def bar(self): return 2
    Foo().bar()   # 2 - the first definition is just gone

A class body executes top to bottom like any other block; a second `def`
with the same name silently rebinds it, the same way a second assignment
to a variable would. No error, no warning - whichever definition is
written last wins, and the first is unreachable dead code.

Several legitimate patterns *look* like duplicate names and are all
excluded: a `@property`/`@x.setter`/`@x.deleter` trio sharing one name,
`@typing.overload` stubs, and `@x.register`-style dispatch (functools
singledispatch). If *any* definition in the group carries one of those
decorators, the whole group is left alone. Branch-conditional redefinition
(`if TYPE_CHECKING: def f(): ...` / `else: def f(): ...`) is naturally
excluded too, since this only looks at a class's direct body statements,
not statements nested inside an `if`.
"""

from __future__ import annotations

import ast
import collections

from codehound.core import Check, Finding


def _is_guard_decorator(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Name):
        return dec.id in ("property", "overload", "staticmethod", "classmethod")
    if isinstance(dec, ast.Attribute):
        return dec.attr in ("setter", "deleter", "getter", "overload", "register")
    return False


class DuplicateMethodDefinition(Check):
    code = "CH076"
    name = "duplicate-method-definition"
    description = "The same method name is defined twice in one class body; the second silently replaces the first."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            by_name: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = collections.defaultdict(list)
            for stmt in cls.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    by_name[stmt.name].append(stmt)
            for name, defs in by_name.items():
                if len(defs) < 2:
                    continue
                if any(_is_guard_decorator(d) for stmt in defs for d in stmt.decorator_list):
                    continue
                last = defs[-1]
                shadowed = defs[:-1]
                lines = ", ".join(str(s.lineno) for s in shadowed)
                findings.append(
                    Finding(
                        path=path,
                        line=last.lineno,
                        col=last.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}.{name}` is defined again here, silently replacing "
                            f"the earlier definition on line(s) {lines} - the earlier one is "
                            f"dead code."
                        ),
                    )
                )
        return findings
