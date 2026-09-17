"""CH027 - ``subprocess.Popen(...)`` never waited on or communicated with.

A `Popen` object is a live child process. Until something calls
`.wait()`, `.communicate()`, or the process is used as a context manager
(both of which reap it on exit), the child stays a zombie in the process
table after it exits, and its stdout/stderr pipe buffers can fill up and
deadlock the child if it writes enough output. `.poll()` alone doesn't
guarantee this - it only reaps if the process has *already* exited by
the time it's called, so a single non-blocking poll right after
`Popen(...)` proves nothing.

Same escape shapes CH009/CH016/CH028 needed to learn the hard way: a
process handle is also "handled" if it's returned (bare or inside a
tuple/list), passed as an argument to another call that takes ownership
of it, or stored as *any* object's attribute - not just a bare
`.wait()`/`.communicate()` in the same function. Real pattern found in
dspy: `lm.process = process` hands the `Popen` off to a different
object entirely, which reaps it later through a separate
`terminate_process(lm.process)` call elsewhere.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function, inside_with_statement

_REAPS = {"wait", "communicate"}


def _is_popen_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "Popen" and isinstance(func.value, ast.Name) and func.value.id == "subprocess"
    if isinstance(func, ast.Name):
        return func.id == "Popen"
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


def _has_reap_call(scope: ast.AST, name: str) -> bool:
    for node in ast.walk(scope):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _REAPS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == name
        ):
            return True
    return False


def _is_passed_as_argument(scope: ast.AST, name: str) -> bool:
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


def _is_stored_as_attribute(scope: ast.AST, name: str) -> bool:
    for node in ast.walk(scope):
        if not isinstance(node, ast.Assign):
            continue
        if isinstance(node.value, ast.Name) and node.value.id == name:
            if any(isinstance(tgt, ast.Attribute) for tgt in node.targets):
                return True
    return False


class UnwaitedSubprocess(Check):
    code = "CH027"
    name = "unwaited-subprocess"
    description = "subprocess.Popen() result never wait()ed or communicate()d with; risks a zombie process."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_popen_call(node.value):
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
                n for r in ast.walk(fn) if isinstance(r, ast.Return) for n in _return_targets(r.value)
            }
            for name in names:
                if (
                    name in returned_names
                    or _has_reap_call(fn, name)
                    or _is_passed_as_argument(fn, name)
                    or _is_stored_as_attribute(fn, name)
                ):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{name} = subprocess.Popen(...)` in `{fn.name}` is never waited on; "
                            f"call `{name}.wait()`/`.communicate()`, or use "
                            f"`with subprocess.Popen(...) as {name}:`."
                        ),
                    )
                )
        return findings
