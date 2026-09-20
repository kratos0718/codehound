"""CH075 - ``__repr__`` calls ``str(self)`` (or formats ``self`` directly),
and the class defines no ``__str__`` of its own.

Verified directly:

    class Bad:
        def __repr__(self):
            return f"Bad({str(self)})"
    repr(Bad())   # RecursionError

``object``'s default ``__str__`` just calls ``__repr__`` - it's the
fallback every class gets for free. So `str(self)` inside `__repr__`,
with no `__str__` override anywhere to catch it first, calls right back
into the same `__repr__` that's still running: infinite recursion,
`RecursionError`, on every single call.

Only fires when the class has no base classes at all (pure `object`
subclass) and defines `__repr__` but not `__str__` directly. A base class
- including a builtin one - is excluded entirely, found for real in
pydantic's `PlainRepr(str)`: subclassing `str` inherits `str`'s own
non-recursive `__str__`, so `str(self)` inside `__repr__` there returns
the string's content directly and never touches `__repr__` at all. The
self-reference itself is one of three unambiguous shapes: `str(self)`, an
f-string embedding `self` directly (`f"{self}"`), or `"{}".format(self)`.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_self_name(node: ast.expr, self_name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == self_name


def _references_self_via_str(node: ast.AST, self_name: str) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "str" and len(node.args) == 1:
            if _is_self_name(node.args[0], self_name):
                return True
        if isinstance(func, ast.Attribute) and func.attr == "format":
            if node.args and any(_is_self_name(a, self_name) for a in node.args):
                return True
    if isinstance(node, ast.JoinedStr):
        for value in node.values:
            if isinstance(value, ast.FormattedValue) and _is_self_name(value.value, self_name):
                return True
    return False


def _defines(cls: ast.ClassDef, method_name: str) -> bool:
    return any(
        isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == method_name for stmt in cls.body
    )


def _has_no_bases(cls: ast.ClassDef) -> bool:
    return not cls.bases


class ReprCallsStrRecursion(Check):
    code = "CH075"
    name = "repr-calls-str-recursion"
    description = "__repr__ calls str(self)/formats self directly with no __str__ defined - object's default __str__ calls back into __repr__, infinite recursion."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if not _has_no_bases(cls):
                continue  # a base (builtin like str/int, or custom) may supply its own safe __str__
            if _defines(cls, "__str__"):
                continue
            repr_method = next(
                (
                    s
                    for s in cls.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == "__repr__"
                ),
                None,
            )
            if repr_method is None or not repr_method.args.args:
                continue
            self_name = repr_method.args.args[0].arg
            hit = next(
                (n for n in ast.walk(repr_method) if n is not repr_method and _references_self_via_str(n, self_name)),
                None,
            )
            if hit is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=hit.lineno,
                    col=hit.col_offset,
                    code=self.code,
                    message=(
                        f"`{cls.name}.__repr__` references `{self_name}` through str()/an "
                        f"f-string, but `{cls.name}` defines no `__str__` - object's default "
                        f"__str__ falls back to __repr__, so this recurses infinitely on "
                        f"every call."
                    ),
                )
            )
        return findings
