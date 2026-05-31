"""CH005 - File handle assigned from ``open()`` without a context manager.

``f = open(path)`` outside a ``with`` block leaks the descriptor unless an
explicit ``f.close()`` runs on every path. Under load this exhausts
``RLIMIT_NOFILE``. CPython's GC eventually reclaims it, but only when the object
dies - which may be never if it is captured in a long-lived attribute.

This check flags an ``open(...)`` whose result is assigned to a name, is not
inside a ``with``, and has no matching ``.close()`` anywhere in the enclosing
function.

Real-world: fixed in agno's ``OpenAITools.transcribe_audio``.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function, inside_with_statement


def _is_open_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"


def _name_targets(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: list[str] = []
        for elt in target.elts:
            out.extend(_name_targets(elt))
        return out
    return []


def _has_close_call(scope: ast.AST, name: str) -> bool:
    for node in ast.walk(scope):
        if isinstance(node, ast.Call):
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "close"
                and isinstance(f.value, ast.Name)
                and f.value.id == name
            ):
                return True
    return False


class UnclosedFileHandle(Check):
    code = "CH005"
    name = "unclosed-file-handle"
    description = "open() result stored without a context manager or matching close()."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_open_call(node.value):
                continue
            if inside_with_statement(node, parents):
                continue
            names: list[str] = []
            for tgt in node.targets:
                names.extend(_name_targets(tgt))
            if not names:
                continue
            fn = enclosing_function(node, parents)
            if fn is None:
                # module/class-level open() is also suspicious, but we focus on
                # function scopes where close-tracking is reliable.
                continue
            # If the function returns the handle, the caller owns closing it.
            returns_handle = any(
                isinstance(n, ast.Return)
                and isinstance(n.value, ast.Name)
                and n.value.id in names
                for n in ast.walk(fn)
            )
            for name in names:
                if returns_handle or _has_close_call(fn, name):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{name} = open(...)` in `{fn.name}` is never closed; "
                            f"use `with open(...) as {name}:`."
                        ),
                    )
                )
        return findings
