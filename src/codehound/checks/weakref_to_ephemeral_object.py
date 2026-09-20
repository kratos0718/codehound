"""CH071 - ``weakref.ref()``/``weakref.proxy()`` targeting an object that was
just constructed inline, with no other reference to keep it alive.

Verified directly: ``w = weakref.ref(Foo())`` - by the time the statement
finishes, nothing but the weakref itself points at that ``Foo()`` instance,
so it is eligible for collection immediately. Calling ``w()`` afterward
returns ``None``, silently, forever - not a crash, just a weakref that was
dead on arrival. The entire point of a weakref is to reference something
*else* is keeping alive; constructing the object as the weakref's own
argument guarantees there is no such "something else".

Only fires when the argument is a direct call expression (the object is
built right there) - a bare name, attribute or subscript might resolve to
something held elsewhere and is left alone, since this check has no way to
know. Calls that look like a getter/cache lookup (``.get``, ``.pop``,
``.find``, ``.fetch``) are also excluded, since those often return an
object that some registry elsewhere is still holding onto.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_GETTER_LIKE = {"get", "pop", "find", "fetch", "load", "read"}


def _is_weakref_call(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name) and func.id in ("ref", "proxy"):
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in ("ref", "proxy"):
        if isinstance(func.value, ast.Name) and func.value.id == "weakref":
            return func.attr
    return None


def _is_getter_like_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    return node.func.attr in _GETTER_LIKE


class WeakrefToEphemeralObject(Check):
    code = "CH071"
    name = "weakref-to-ephemeral-object"
    description = "weakref.ref()/proxy() targets a freshly constructed object with no other reference keeping it alive."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            kind = _is_weakref_call(node)
            if kind is None:
                continue
            if not node.args:
                continue
            target = node.args[0]
            if not isinstance(target, ast.Call):
                continue
            if _is_getter_like_call(target):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"weakref.{kind}() targets an object constructed inline as its own "
                        f"argument - nothing else holds a reference to it, so it can be "
                        f"collected before the weakref is ever used, and calling it back "
                        f"returns None silently."
                    ),
                )
            )
        return findings
