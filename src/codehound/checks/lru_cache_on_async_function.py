"""CH030 - ``@lru_cache``/``@cache`` on an ``async def`` caches the coroutine object, not its result.

`functools.lru_cache` has no idea what a coroutine is - it just
memoizes whatever the decorated callable returns for a given set of
arguments. Calling an `async def` function doesn't run its body at all;
it just constructs a coroutine object. So `lru_cache` ends up caching
*that object*, and returns the exact same one on every call with the
same arguments - including the second, third, and every later one.
Verified directly:

    @lru_cache
    async def fetch(x):
        return x * 2

    async def main():
        await fetch(1)
        await fetch(1)  # RuntimeError: cannot reuse already awaited coroutine

The second `await` crashes immediately, every time, for any arguments
that repeat - unlike CH011 (`lru_cache` leaking `self` on a *sync*
instance method), this is a correctness bug on the very next call, not
a slow memory leak, and it fires on module-level functions too, not
just methods.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_CACHE_DECORATOR_NAMES = {"lru_cache", "cache"}


def _is_cache_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id in _CACHE_DECORATOR_NAMES
    if isinstance(target, ast.Attribute):
        return target.attr in _CACHE_DECORATOR_NAMES
    return False


class LruCacheOnAsyncFunction(Check):
    code = "CH030"
    name = "lru-cache-on-async-function"
    description = "@lru_cache/@cache on an async def caches the coroutine object, not its awaited result."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for dec in node.decorator_list:
                if not _is_cache_decorator(dec):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{node.name}` is `async def` decorated with a cache that has no "
                            f"idea what a coroutine is - it caches the coroutine *object*, not "
                            f"its awaited result. The second call with the same arguments "
                            f"raises `RuntimeError: cannot reuse already awaited coroutine`. "
                            f"Cache the result inside the function body instead, or use a "
                            f"cache designed for coroutines (e.g. `asyncache`'s `@cached`)."
                        ),
                    )
                )
                break
        return findings
