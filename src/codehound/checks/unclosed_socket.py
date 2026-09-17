"""CH016 - ``socket.socket(...)`` assigned without a context manager or ``.close()``.

The same shape as CH005's unclosed file handle, for a different resource:
`s = socket.socket(...)` outside a `with` block, with no matching
`s.close()` anywhere in the function and no ownership hand-off, leaks the
file descriptor exactly like an unclosed file does - sockets are file
descriptors on POSIX systems, and Python's socket module supports the
context-manager protocol specifically so this doesn't happen.

Unlike a file handle, a socket used for rendezvous/handshake code is
routinely handed off by passing it into another call rather than by
`return`ing it bare or closing it locally - real false positives found in
vllm's distributed process-group setup: `return port, s` (returned inside
a tuple, not as the bare name), `socks.append(s)` with the list itself
returned, and `listen_socket=listen_socket` passed straight into a
`create_tcp_store(...)` call that takes ownership of it. So a socket name
is also treated as escaped if it's returned as part of a tuple/list, or
passed as an argument to any call other than a method called *on* the
socket itself (`s.bind(...)`, `s.close()`, etc., where the socket is the
receiver, not an argument).
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


def _is_passed_as_argument(scope: ast.AST, name: str) -> bool:
    """Is `name` ever passed into a call as an argument (not as the receiver
    of an attribute call, e.g. `name.bind(...)`)? A socket handed to another
    call - `store_it(s)`, `things.append(s)`, `f(listen_socket=s)` - has its
    ownership transferred there, same as a `return`."""
    for node in ast.walk(scope):
        if not isinstance(node, ast.Call):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id == name:
                return True
        for kw in node.keywords:
            if isinstance(kw.value, ast.Name) and kw.value.id == name:
                return True
    return False


def _return_targets(value: ast.expr | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, ast.Name):
        return [value.id]
    if isinstance(value, (ast.Tuple, ast.List)):
        out: list[str] = []
        for elt in value.elts:
            out.extend(_return_targets(elt))
        return out
    return []


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
            returned_names = {
                n
                for r in ast.walk(fn)
                if isinstance(r, ast.Return)
                for n in _return_targets(r.value)
            }
            for name in names:
                if (
                    name in returned_names
                    or _has_close_call(fn, name)
                    or _is_passed_as_argument(fn, name)
                ):
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
