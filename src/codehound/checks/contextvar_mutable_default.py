"""CH069 - ``contextvars.ContextVar(name, default=mutable)`` returns the
*same* object from every context that never explicitly set it, when
something actually mutates it in place.

Verified directly: ``var = ContextVar('items', default=[])``, then calling
``var.get().append(x)`` from two different contexts that never call
``var.set(...)`` first both mutate the exact same list - `var.get() is
var.get()` is `True` across calls in different contexts. `ContextVar`'s
default is stored once and handed back as-is, not copied per context.

Only fires when the module also does a direct mutation on this specific
variable's own ``.get()`` result (``var.get().append(...)``, `var.get()[k]
= v`, etc.) - a mutable default alone isn't the bug, the same way CH002's
default argument isn't dangerous until it's actually mutated. The first
corpus scan found every single real-world hit (letta, llama_index,
qdrant-client, pydantic-ai) already follows the correct, defensive
pattern - `current = var.get().copy(); current[...] = ...; var.set(current)`,
or reading a fresh dict via `{**var.get(), **more}` before `.set()` - never
mutating the shared object in place. Narrowed to require proof of an
actual in-place mutation on the un-copied `.get()` result, which is the
one shape that's genuinely broken.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_MUTATING_METHODS = {"append", "extend", "insert", "remove", "pop", "clear", "update", "add", "discard", "popitem"}


def _is_contextvar_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "ContextVar"
    return isinstance(func, ast.Attribute) and func.attr == "ContextVar"


def _is_mutable_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set")


def _is_get_call_on(node: ast.expr, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and not node.args
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == name
    )


def _has_unsafe_direct_mutation(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        # name.get().mutating_method(...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
            and _is_get_call_on(node.func.value, name)
        ):
            return True
        # name.get()[key] = value
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and _is_get_call_on(node.value, name):
            return True
    return False


class ContextvarMutableDefault(Check):
    code = "CH069"
    name = "contextvar-mutable-default"
    description = "A ContextVar's mutable default is mutated in place on .get(), shared across every context."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not _is_contextvar_call(node):
                continue
            default = next((kw.value for kw in node.keywords if kw.arg == "default"), None)
            if default is None and len(node.args) >= 2:
                default = node.args[1]
            if default is None or not _is_mutable_literal(default):
                continue
            assign = parents.get(id(node))
            if not (
                isinstance(assign, ast.Assign) and len(assign.targets) == 1 and isinstance(assign.targets[0], ast.Name)
            ):
                continue
            var_name = assign.targets[0].id
            if not _has_unsafe_direct_mutation(tree, var_name):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{var_name}`'s default is a mutable literal, and it's mutated "
                        f"directly on `.get()` elsewhere in this file - every context that "
                        f"never calls `.set(...)` first shares that same object."
                    ),
                )
            )
        return findings
