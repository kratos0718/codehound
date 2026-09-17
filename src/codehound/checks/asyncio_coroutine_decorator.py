"""CH022 - ``@asyncio.coroutine`` was removed in Python 3.11.

The generator-based coroutine decorator predates `async def` (added in
3.5) and was kept around for years as a bridge for old code, deprecated
since 3.8 with an explicit `DeprecationWarning`, then removed outright in
3.11 - `AttributeError: module 'asyncio' has no attribute 'coroutine'`
the moment the decorator line runs, not something that surfaces later.
`async def` is the direct replacement; there's no decorator to swap in.

A bare `@coroutine` is only trusted to mean `asyncio.coroutine` if the
file actually imported it via `from asyncio import coroutine` - the same
name-collision guard CH018 uses for `Task`, since `coroutine` alone is
common enough to plausibly be someone's own decorator.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _imports_coroutine_from_asyncio(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "asyncio":
            if any(alias.name == "coroutine" for alias in node.names):
                return True
    return False


def _is_asyncio_coroutine_attr(node: ast.expr) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "coroutine"
        and isinstance(node.value, ast.Name)
        and node.value.id == "asyncio"
    )


class AsyncioCoroutineDecorator(Check):
    code = "CH022"
    name = "removed-asyncio-coroutine-decorator"
    description = "@asyncio.coroutine was removed in Python 3.11; use `async def` instead."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        trust_bare_name = _imports_coroutine_from_asyncio(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                is_match = _is_asyncio_coroutine_attr(dec) or (
                    trust_bare_name and isinstance(dec, ast.Name) and dec.id == "coroutine"
                )
                if not is_match:
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=dec.lineno,
                        col=dec.col_offset,
                        code=self.code,
                        message=(
                            f"`@{ast.unparse(dec)}` on `{node.name}` - removed in Python 3.11; "
                            f"define `{node.name}` with `async def` instead."
                        ),
                    )
                )
                break
        return findings
