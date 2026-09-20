"""CH064 - ``asyncio.wait([coro(), ...])`` passed a bare coroutine call
instead of a Task.

Verified directly on Python 3.13: ``await asyncio.wait([some_coroutine()])``
raises ``TypeError: Passing coroutines is forbidden, use tasks
explicitly.`` - passing coroutine objects to ``asyncio.wait()`` was
deprecated in 3.8 and became a hard error in 3.11. Code copied from an
older tutorial, or written against an older Python, still parses and
still runs the coroutine (with just a ``DeprecationWarning``) on 3.8-3.10,
then breaks outright the moment it runs on 3.11+.

Only fires on a direct function-call expression inside the list/tuple/set
literal passed to ``asyncio.wait`` - a bare name (`tasks = [t1, t2];
asyncio.wait(tasks)`, the overwhelmingly common, correct shape) can't be
proven to be a raw coroutine without type inference, so it's left alone;
a call already wrapped in ``asyncio.create_task``/``asyncio.ensure_future``
is the correct form and is also left alone.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_TASK_WRAPPERS = {"create_task", "ensure_future"}


def _is_task_wrapped(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _TASK_WRAPPERS
    return isinstance(func, ast.Attribute) and func.attr in _TASK_WRAPPERS


def _is_asyncio_wait_call(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "wait"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
    )


class AsyncioWaitBareCoroutine(Check):
    code = "CH064"
    name = "asyncio-wait-bare-coroutine"
    description = "asyncio.wait([...]) is given a bare coroutine call instead of a Task - a TypeError on 3.11+."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not _is_asyncio_wait_call(node) or not node.args:
                continue
            container = node.args[0]
            if not isinstance(container, (ast.List, ast.Tuple, ast.Set)):
                continue
            for elt in container.elts:
                if isinstance(elt, ast.Call) and not _is_task_wrapped(elt):
                    findings.append(
                        Finding(
                            path=path,
                            line=elt.lineno,
                            col=elt.col_offset,
                            code=self.code,
                            message=(
                                "This is a bare coroutine call, not a Task - `asyncio.wait()` "
                                "raises `TypeError: Passing coroutines is forbidden` on Python "
                                "3.11+. Wrap it: `asyncio.create_task(...)`."
                            ),
                        )
                    )
        return findings
