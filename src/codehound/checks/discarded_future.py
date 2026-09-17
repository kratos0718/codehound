"""CH013 - ``executor.submit(...)`` result discarded; a worker exception is lost silently.

``ThreadPoolExecutor``/``ProcessPoolExecutor.submit(...)`` returns a
``Future`` immediately - the submitted callable runs on a worker, and if it
raises, that exception is stored *on the Future* rather than propagated.
Nothing surfaces it unless something later calls ``.result()`` (or
``.exception()``) on that specific Future. A bare, uncaptured
``executor.submit(fn, ...)`` throws the Future away entirely: the work
still runs, but a failure in it disappears without a trace - no traceback,
no log line, nothing. This is the executor-based cousin of CH006's
floating-task, and a distinct failure mode from CH005/CH009's leaks: here
the *cleanup* isn't the problem, the *silent loss of a real error* is.

Tracks variables assigned from ``ThreadPoolExecutor(...)`` /
``ProcessPoolExecutor(...)`` (bare or ``concurrent.futures.``-qualified),
including a ``with ... as executor:`` binding, and only flags a bare
expression-statement ``.submit(...)`` call on one of them - matching
CH006's own precision bar: the result must be completely unreachable, not
merely "not called with `.result()` yet".
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_EXECUTOR_NAMES = {"ThreadPoolExecutor", "ProcessPoolExecutor"}


def _is_executor_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _EXECUTOR_NAMES
    if isinstance(func, ast.Attribute):
        return func.attr in _EXECUTOR_NAMES
    return False


def _tracked_executor_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and _is_executor_call(node.value):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    names.add(tgt.id)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if _is_executor_call(item.context_expr) and isinstance(item.optional_vars, ast.Name):
                    names.add(item.optional_vars.id)
    return names


class DiscardedFuture(Check):
    code = "CH013"
    name = "discarded-future"
    description = "executor.submit(...) result discarded; a worker exception is silently lost."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        executor_names = _tracked_executor_names(tree)
        if not executor_names:
            return []

        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            func = call.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "submit"
                and isinstance(func.value, ast.Name)
                and func.value.id in executor_names
            ):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{func.value.id}.submit(...)` result is discarded; if the submitted "
                        f"work raises, the exception is stored on the Future and never seen. "
                        f"Keep the Future and call `.result()`/`.exception()`, or pass it to "
                        f"`concurrent.futures.wait()`/`as_completed()`."
                    ),
                )
            )
        return findings
