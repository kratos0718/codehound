"""CH016 - ``socket.socket(...)`` assigned without a context manager or ``.close()``.

The same shape as CH005's unclosed file handle, for a different resource:
`s = socket.socket(...)` outside a `with` block, with no matching
`s.close()` anywhere in the function and no `return`ed ownership hand-off,
leaks the file descriptor exactly like an unclosed file does - sockets are
file descriptors on POSIX systems, and Python's socket module supports
the context-manager protocol specifically so this doesn't happen.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function, inside_with_statement


def _is_socket_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "socket" and isinstance(func.value, ast.Name) and func.value.id == "socket"
    if isinstance(func, ast.Name):
        return func.id == "socket"
    return False


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
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "close"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
        ):
            return True
    return False


class UnclosedSocket(Check):
    code = "CH016"
    name = "unclosed-socket"
    description = "socket.socket() result stored without a context manager or matching close()."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_socket_call(node.value):
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
                continue
            returns_socket = any(
                isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id in names
                for n in ast.walk(fn)
            )
            for name in names:
                if returns_socket or _has_close_call(fn, name):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{name} = socket.socket(...)` in `{fn.name}` is never closed; "
                            f"use `with socket.socket(...) as {name}:`."
                        ),
                    )
                )
        return findings
