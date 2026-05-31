"""CH006 - Fire-and-forget asyncio task (Ruff RUF006).

``asyncio.create_task(...)`` / ``asyncio.ensure_future(...)`` whose result is
discarded is a real, hard-to-debug bug: the event loop keeps only a *weak*
reference to the task, so it can be garbage-collected before it finishes,
silently cancelling the work mid-flight. The fix is to keep a strong reference
(store it in a set, await it, or hand it to a TaskGroup).

This finds expression-statement calls (result not assigned/awaited/returned) to
``asyncio.create_task``, ``asyncio.ensure_future`` or ``<loop>.create_task``.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_CREATORS = {"create_task", "ensure_future"}


class FloatingTask(Check):
    code = "CH006"
    name = "floating-task"
    description = "Result of create_task()/ensure_future() discarded; task may be GC'd before completion."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            # Only bare expression statements: `asyncio.create_task(...)` on its own line.
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            func = call.func
            if not isinstance(func, ast.Attribute) or func.attr not in _CREATORS:
                continue
            value = func.value
            if not isinstance(value, ast.Name):
                continue
            owner = value.id
            # asyncio.create_task / asyncio.ensure_future, or a loop-ish receiver.
            is_asyncio = owner == "asyncio"
            is_loop = "loop" in owner.lower()
            if not (is_asyncio or is_loop):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{owner}.{func.attr}(...)` result is discarded; keep a reference "
                        f"(the loop only holds a weak ref, so the task may be GC'd mid-run)."
                    ),
                )
            )
        return findings
