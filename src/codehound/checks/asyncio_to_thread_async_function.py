"""CH093 - ``asyncio.to_thread(async_func)`` given a coroutine function
instead of a plain sync one.

Verified directly:

    async def async_worker():
        print("body executing")
        return 42

    async def main():
        result = await asyncio.to_thread(async_worker)
        print(result)

    # nothing printed from async_worker; result is a live, never-awaited
    # coroutine object, plus a "coroutine was never awaited" RuntimeWarning

`asyncio.to_thread` runs its callable in a worker thread via
`functools.partial(func, *args, **kwargs)` and just calls it - for an
`async def`, calling it doesn't run the body at all, it only
*constructs* a coroutine object. That object gets returned as
`to_thread`'s result, silently, with the coroutine's own body never
having executed and no error anywhere except a background
RuntimeWarning easy to miss in CI log noise.

Only fires when the function passed to `asyncio.to_thread` is a bare
name that resolves to a same-file, module-level `async def` -  the
same same-file resolution CH007 already uses for the identical
underlying mistake (calling an async function synchronously) at a
different call site.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class AsyncioToThreadAsyncFunction(Check):
    code = "CH093"
    name = "asyncio-to-thread-async-function"
    description = "asyncio.to_thread() given an async function - it only constructs the coroutine, never runs its body."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        async_defs = {
            node.name for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
        } if isinstance(tree, ast.Module) else set()
        if not async_defs:
            return findings
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_to_thread = (isinstance(func, ast.Name) and func.id == "to_thread") or (
                isinstance(func, ast.Attribute) and func.attr == "to_thread"
            )
            if not is_to_thread or not node.args:
                continue
            target = node.args[0]
            if isinstance(target, ast.Name) and target.id in async_defs:
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"asyncio.to_thread() is given `{target.id}`, an async function - "
                            f"to_thread just calls it in a worker thread, which only "
                            f"constructs a coroutine object without running its body. The "
                            f"result is a never-awaited coroutine, not `{target.id}`'s return value."
                        ),
                    )
                )
        return findings
