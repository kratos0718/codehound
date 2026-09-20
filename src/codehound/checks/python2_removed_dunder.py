"""CH082 - a Python 2 special method that Python 3 no longer looks up at
all is defined in a class.

Verified directly:

    class Old:
        def __nonzero__(self): return False   # should be __bool__
        def __unicode__(self): return "text"   # should be __str__
    bool(Old())   # True - __nonzero__ is never consulted
    str(Old())     # default repr-ish string - __unicode__ is never consulted

Python 3 renamed or removed a handful of special methods, and unlike a
typo'd regular method name, defining the old one raises nothing anywhere
- it's just a plain method that Python's dunder-dispatch machinery never
looks for, ever, because it looks for a different name (or nothing at
all). Pure dead code, and unlike most dead code, it silently disables the
behavior the class was clearly trying to implement.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_REMOVED_OR_RENAMED = {
    "__nonzero__": "__bool__",
    "__unicode__": "__str__",
    "__cmp__": None,
    "__div__": "__truediv__",
    "__idiv__": "__itruediv__",
    "__rdiv__": "__rtruediv__",
    "__long__": None,
    "__hex__": None,
    "__oct__": None,
    "__coerce__": None,
    "__getslice__": "__getitem__ with a slice",
    "__setslice__": "__setitem__ with a slice",
    "__delslice__": "__delitem__ with a slice",
}


class Python2RemovedDunder(Check):
    code = "CH082"
    name = "python2-removed-dunder"
    description = "A Python 2 special method (e.g. __nonzero__, __unicode__, __cmp__) is defined - Python 3 never looks it up, silently dead."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for stmt in cls.body:
                if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                replacement = _REMOVED_OR_RENAMED.get(stmt.name)
                if stmt.name not in _REMOVED_OR_RENAMED:
                    continue
                suffix = f" - use {replacement} instead" if replacement else " - there is no Python 3 replacement"
                findings.append(
                    Finding(
                        path=path,
                        line=stmt.lineno,
                        col=stmt.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}.{stmt.name}` is a Python 2 special method - Python 3 "
                            f"never looks it up{suffix}. Silently dead code, not a typo Python "
                            f"will ever complain about."
                        ),
                    )
                )
        return findings
