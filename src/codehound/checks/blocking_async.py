"""CH001 - Blocking call inside an async function.

A synchronous, blocking call (``time.sleep``, ``requests.get`` ...) executed
directly inside an ``async def`` freezes the *entire* event loop: every other
coroutine, task and the agent loop itself stalls for the duration of the call.
The fix is the async equivalent (``await asyncio.sleep``, ``httpx.AsyncClient``,
``loop.run_in_executor`` ...).

Real-world: this is exactly the bug fixed in agno's Couchbase vector store,
where ``time.sleep(1)`` sat inside ``_async_create_collection_and_scope``.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function, is_awaited

# (module, attribute) pairs that block the calling thread.
_BLOCKING_CALLS = {
    ("time", "sleep"),
    ("requests", "get"),
    ("requests", "post"),
    ("requests", "put"),
    ("requests", "delete"),
    ("requests", "patch"),
    ("requests", "head"),
    ("requests", "request"),
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("os", "system"),
    ("urllib.request", "urlopen"),
}


class BlockingCallInAsync(Check):
    code = "CH001"
    name = "blocking-call-in-async"
    description = "Synchronous blocking call inside an async function freezes the event loop."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            value = func.value
            # resolve dotted module prefix (e.g. urllib.request)
            if isinstance(value, ast.Name):
                module = value.id
            elif isinstance(value, ast.Attribute):
                parts = []
                cur = value
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    parts.append(cur.id)
                module = ".".join(reversed(parts))
            else:
                continue
            if (module, func.attr) not in _BLOCKING_CALLS:
                continue
            # An awaited call (e.g. `await client.post(...)`) does not block the
            # event loop, even if the receiver name collides with a sync library.
            if is_awaited(node, parents):
                continue
            fn = enclosing_function(node, parents)
            if fn is None or not isinstance(fn, ast.AsyncFunctionDef):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{module}.{func.attr}()` blocks the event loop inside "
                        f"async function `{fn.name}`; use the async equivalent."
                    ),
                )
            )
        return findings
