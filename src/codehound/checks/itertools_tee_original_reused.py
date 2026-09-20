"""CH072 - the original iterator passed to ``itertools.tee()`` is iterated
again afterward.

Verified directly:

    it = iter([1, 2, 3, 4, 5])
    a, b = itertools.tee(it, 2)
    next(it)          # advances the ORIGINAL
    list(a)            # [2, 3, 4, 5] - the "1" is gone from BOTH copies
    list(b)            # [2, 3, 4, 5]

``itertools.tee``'s own documentation says this outright: "once tee() has
made a split, the original iterable should not be used anywhere else;
otherwise, the iterable could get advanced without the tee objects being
informed." Advancing the original doesn't raise - it silently desyncs
every tee'd copy, dropping elements from all of them at once.

Only fires when the teed expression is a bare name (so a later use of that
exact name, after the tee call, can be matched by identity) and the later
use is one of the ways an iterator actually gets advanced: a ``for``
loop's iterable, ``next(name)``, or another ``list``/``tuple``/``sorted``
call wrapping it directly.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function

_CONSUMING_BUILTINS = {"next", "list", "tuple", "sorted", "sum", "set", "min", "max"}


def _tee_target_name(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    is_tee = (isinstance(func, ast.Name) and func.id == "tee") or (
        isinstance(func, ast.Attribute) and func.attr == "tee"
    )
    if not is_tee or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Name):
        return first.id
    return None


def _consumes_name(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.For) and isinstance(node.iter, ast.Name) and node.iter.id == name:
        return True
    if isinstance(node, ast.Call):
        if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == name:
            if isinstance(node.func, ast.Name) and node.func.id in _CONSUMING_BUILTINS:
                return True
    return False


class IteratorTeeOriginalReused(Check):
    code = "CH072"
    name = "itertools-tee-original-reused"
    description = "The original iterator passed to itertools.tee() is iterated again afterward, silently desyncing every copy."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            name = _tee_target_name(node.value)
            if name is None:
                continue
            scope = enclosing_function(node, parents) or tree
            hit = None
            for later in ast.walk(scope):
                if getattr(later, "lineno", -1) <= node.lineno:
                    continue
                if later is node.value:
                    continue
                if _consumes_name(later, name):
                    hit = later
                    break
            if hit is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=hit.lineno,
                    col=hit.col_offset,
                    code=self.code,
                    message=(
                        f"`{name}` was passed to itertools.tee() and is iterated again here - "
                        f"once tee() splits an iterator, advancing the original desyncs every "
                        f"tee'd copy, silently dropping elements from all of them."
                    ),
                )
            )
        return findings
