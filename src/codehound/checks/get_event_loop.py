"""CH004 - Deprecated ``asyncio.get_event_loop()``.

Calling ``asyncio.get_event_loop()`` when there is no running loop is deprecated
since Python 3.10 and emits a ``DeprecationWarning`` from 3.12. Inside a
coroutine, use ``asyncio.get_running_loop()``; to run a coroutine from sync
code, use ``asyncio.run()``.

Real-world: fixed in crewAI's structured-tool / Snowflake search tool.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class DeprecatedGetEventLoop(Check):
    code = "CH004"
    name = "deprecated-get-event-loop"
    description = "asyncio.get_event_loop() is deprecated outside a running loop."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get_event_loop"
                and isinstance(func.value, ast.Name)
                and func.value.id == "asyncio"
            ):
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            "`asyncio.get_event_loop()` is deprecated; use "
                            "`asyncio.get_running_loop()` (in async) or `asyncio.run()`."
                        ),
                    )
                )
        return findings
