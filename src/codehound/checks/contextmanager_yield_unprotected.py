"""CH047 - ``@contextmanager`` cleanup after ``yield`` doesn't run if the body raises.

`@contextlib.contextmanager` turns a generator into a context manager
by running everything up to `yield` on `__enter__` and everything after
it on `__exit__` - but if the `with`-block's body raises, Python
re-raises that exception *at the yield statement itself*. Any cleanup
code written after `yield`, with no `try`/`finally` wrapping it, simply
never runs on that path. Verified directly:

    @contextlib.contextmanager
    def resource():
        opened.append(1)
        yield "handle"
        closed.append(1)   # cleanup - never reached below

    with resource() as h:
        raise RuntimeError("boom")
    # opened: 1, closed: 0 - the exception skipped the cleanup entirely

This is the exact inverse of what a context manager exists for: the
whole point of `with` is "this cleanup runs no matter how the block
exits," and a generator-based one silently doesn't unless the author
remembers `try`/`finally` around the `yield` themselves - unlike a
class-based context manager, where `__exit__` is a separate method
Python always calls regardless.

Flags a function decorated `@contextlib.contextmanager` (or
`@contextlib.asynccontextmanager`, or a bare `@contextmanager`/
`@asynccontextmanager` if the corresponding name was actually imported
from `contextlib`) that has code after its `yield` with nothing
protecting it - either the `yield` is a bare top-level statement in
the function body with more statements after it, or it's inside a
`try` with no `finally` and more statements after it within that same
`try` body. Deliberately narrow: doesn't try to reason about `except`
handlers that partially protect the cleanup, nested `if`/`else`
branches after the `yield`, or any shape beyond these two - a
generator with exactly one `yield` and nothing after it needs no
`finally` at all, and this check has nothing to say about it.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_CONTEXTMANAGER_NAMES = {"contextmanager", "asynccontextmanager"}


def _decorator_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in func.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _imported_bare_contextmanager_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "contextlib":
            for alias in node.names:
                if alias.name in _CONTEXTMANAGER_NAMES:
                    names.add(alias.asname or alias.name)
    return names


def _is_contextmanager_function(func: ast.FunctionDef | ast.AsyncFunctionDef, bare_names: set[str]) -> bool:
    decorators = _decorator_names(func)
    return bool(decorators & _CONTEXTMANAGER_NAMES) or bool(decorators & bare_names)


def _yield_of(stmt: ast.stmt) -> ast.Yield | None:
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield):
        return stmt.value
    if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Yield):
        return stmt.value
    return None


def _unprotected_yield_in_block(block: list[ast.stmt], has_finally: bool) -> ast.Yield | None:
    """A bare `yield` in `block` with statements after it, where nothing
    in this exact block guarantees they still run on an exception."""
    for i, stmt in enumerate(block):
        yield_node = _yield_of(stmt)
        if yield_node is not None:
            if i + 1 < len(block) and not has_finally:
                return yield_node
            return None
        if isinstance(stmt, ast.Try):
            inner = _unprotected_yield_in_block(stmt.body, bool(stmt.finalbody))
            if inner is not None:
                return inner
    return None


class ContextmanagerYieldUnprotected(Check):
    code = "CH047"
    name = "contextmanager-yield-unprotected"
    description = "@contextmanager cleanup after yield doesn't run if the with-block body raises, unless wrapped in try/finally."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        bare_names = _imported_bare_contextmanager_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_contextmanager_function(node, bare_names):
                continue
            yield_node = _unprotected_yield_in_block(node.body, has_finally=False)
            if yield_node is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=yield_node.lineno,
                    col=yield_node.col_offset,
                    code=self.code,
                    message=(
                        "code after this `yield` only runs if the with-block body doesn't raise "
                        "- wrap the `yield` in `try:`/`finally:` so cleanup runs unconditionally, "
                        "the same guarantee a class-based context manager's `__exit__` gets for "
                        "free."
                    ),
                )
            )
        return findings
