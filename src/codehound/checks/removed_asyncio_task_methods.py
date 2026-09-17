"""CH018 - ``asyncio.Task.current_task()`` / ``.all_tasks()`` were removed.

Both were classmethods on ``asyncio.Task``, deprecated since 3.7 in favor of
the module-level ``asyncio.current_task()`` / ``asyncio.all_tasks()``, and
removed outright in 3.9. Code that still calls them through ``Task``
raises ``AttributeError`` immediately, every time, the same "fails on
first use" shape as CH008's ``asyncio.run()``-in-a-running-loop.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_REMOVED_METHODS = {"current_task", "all_tasks"}


class RemovedAsyncioTaskMethods(Check):
    code = "CH018"
    name = "removed-asyncio-task-methods"
    description = "asyncio.Task.current_task()/.all_tasks() were removed in 3.9; use the module-level functions."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        # A bare `Task` name is only trusted to mean asyncio.Task if this file
        # actually imported it from asyncio - "Task" is generic enough (Celery,
        # a dataclass, ...) that matching it unconditionally would be a real
        # false-positive risk, the same lesson CH007's name-collision false
        # positives already taught this project.
        task_imported_from_asyncio = any(
            isinstance(n, ast.ImportFrom) and n.module == "asyncio" and any(a.name == "Task" for a in n.names)
            for n in ast.walk(tree)
        )

        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in _REMOVED_METHODS):
                continue
            receiver = func.value
            is_asyncio_task = (
                isinstance(receiver, ast.Attribute)
                and receiver.attr == "Task"
                and isinstance(receiver.value, ast.Name)
                and receiver.value.id == "asyncio"
            )
            is_bare_task = (
                task_imported_from_asyncio and isinstance(receiver, ast.Name) and receiver.id == "Task"
            )
            if not (is_asyncio_task or is_bare_task):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`Task.{func.attr}(...)` was removed in Python 3.9; use "
                        f"`asyncio.{func.attr}(...)` instead."
                    ),
                )
            )
        return findings
