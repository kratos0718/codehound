"""CH031 - ``multiprocessing.Pool()`` never closed or terminated.

A `Pool` starts its worker processes at construction time. Until
`.close()` (graceful, finishes queued work first) or `.terminate()`
(immediate) is called - and normally `.join()` after `.close()` to
reap them - those worker processes keep running, each holding its own
copy of the parent's memory, for as long as the parent process lives.
Same resource-leak shape as CH027's `subprocess.Popen`, CH009's
`threading.Thread`, and CH012's `multiprocessing.Process`, just for a
whole pool of them at once, and Python's own docs recommend the
context-manager form specifically to avoid this.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function, inside_with_statement

_RELEASES = {"close", "terminate"}


def _is_pool_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "Pool" and isinstance(func.value, ast.Name) and func.value.id in (
            "multiprocessing",
            "mp",
        )
    if isinstance(func, ast.Name):
        return func.id == "Pool"
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


def _has_release_call(scope: ast.AST, name: str) -> bool:
    for node in ast.walk(scope):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _RELEASES
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


class UnclosedPool(Check):
    code = "CH031"
    name = "unclosed-pool"
    description = "multiprocessing.Pool() never closed or terminated; worker processes leak."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_pool_call(node.value):
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
                    or _has_release_call(fn, name)
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
                            f"`{name} = multiprocessing.Pool(...)` in `{fn.name}` is never "
                            f"closed or terminated; its worker processes keep running for the "
                            f"life of the parent. Call `{name}.close()`/`.join()` (or "
                            f"`.terminate()`), or use `with multiprocessing.Pool(...) as {name}:`."
                        ),
                    )
                )
        return findings
