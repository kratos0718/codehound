"""CH008 - ``asyncio.run()`` called while a loop is already running.

``asyncio.run()`` creates a new event loop and refuses to run if one is
already active on the current thread - calling it from inside a coroutine
raises ``RuntimeError: asyncio.run() cannot be called from a running event
loop`` immediately, every time, unconditionally. Unlike most of the other
checks here, this isn't a subtle production-only failure; it fails the
first time the code path executes. It shows up anyway, usually from a
function that was written and tested as a synchronous entry point, then
got called from newly-async'd calling code without anyone changing its
body.

Scoped to the *immediate* enclosing function only, matching how the other
checks avoid cross-function analysis: `async def outer(): def inner():
asyncio.run(...)` does not flag, since `inner` is nested but still
synchronous itself - whether calling it while a loop is running is
actually safe depends on what thread it runs on, which this checker has
no way to know.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


class AsyncioRunInRunningLoop(Check):
    code = "CH008"
    name = "asyncio-run-in-running-loop"
    description = "asyncio.run() called from inside an async function; always raises RuntimeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
            ):
                continue
            fn = enclosing_function(node, parents)
            if not isinstance(fn, ast.AsyncFunctionDef):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`asyncio.run(...)` inside async function `{fn.name}` always raises "
                        f"RuntimeError - a loop is already running here; `await` the coroutine "
                        f"directly instead."
                    ),
                )
            )
        return findings
