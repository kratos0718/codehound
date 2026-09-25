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
import re
import string

from codehound.core import Check, Finding


def _is_self_name(node: ast.expr, self_name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == self_name


def _module_string_constants(tree: ast.AST) -> dict[str, str]:
    consts: dict[str, str] = {}
    body = tree.body if isinstance(tree, ast.Module) else []
    for stmt in body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        ):
            consts[stmt.targets[0].id] = stmt.value.value
    return consts


def _format_renders_self_bare(call: ast.Call, self_name: str, consts: dict[str, str]) -> bool:
    """`fmt.format(..., self, ...)` recurses only if a field renders `self` bare.

    `{0}`, `{}`, `{0!r}`, `{0!s}` all end up in str()/repr() of self;
    `{0.hostname}` / `{0[key]}` only read into it (celery's `Worker.__repr__`
    is `R_WORKER.format(self)` with `R_WORKER = '<Worker: {0.hostname} ...>'`).
    An unresolvable format string is skipped rather than guessed at.
    """
    receiver = call.func.value  # type: ignore[union-attr]
    if isinstance(receiver, ast.Constant) and isinstance(receiver.value, str):
        fmt = receiver.value
    elif isinstance(receiver, ast.Name) and receiver.id in consts:
        fmt = consts[receiver.id]
    else:
        return False
    self_positions = {i for i, a in enumerate(call.args) if _is_self_name(a, self_name)}
    self_keywords = {kw.arg for kw in call.keywords if kw.arg and _is_self_name(kw.value, self_name)}
    if not self_positions and not self_keywords:
        return False
    try:
        fields = list(string.Formatter().parse(fmt))
    except ValueError:
        return False
    auto_index = 0
    for _literal, field_name, _spec, _conversion in fields:
        if field_name is None:
            continue
        first = re.split(r"[.\[]", field_name, maxsplit=1)[0]
        bare = field_name == first
        if first == "":
            ref: int | str = auto_index
            auto_index += 1
        elif first.isdigit():
            ref = int(first)
        else:
            ref = first
        refers_to_self = ref in self_positions if isinstance(ref, int) else ref in self_keywords
        if refers_to_self and bare:
            return True
    return False


def _references_self_via_str(node: ast.AST, self_name: str, consts: dict[str, str]) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id == "str" and len(node.args) == 1:
            if _is_self_name(node.args[0], self_name):
                return True
        if isinstance(func, ast.Attribute) and func.attr == "format":
            if _format_renders_self_bare(node, self_name, consts):
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
        consts = _module_string_constants(tree)
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
                (n for n in ast.walk(repr_method) if n is not repr_method and _references_self_via_str(n, self_name, consts)),
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
