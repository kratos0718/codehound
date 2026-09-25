"""CH007 - Coroutine called without ``await`` (or scheduling).

Calling an ``async def`` function produces a coroutine object; it does not run
any of the function's body until something ``await``s it, wraps it in
``asyncio.create_task``/``asyncio.gather``, or otherwise drives it. A bare
``foo()`` where ``foo`` is a coroutine function, used as a standalone
statement, creates the coroutine and immediately discards it - the work
inside never executes at all, and Python emits a
``RuntimeWarning: coroutine 'foo' was never awaited`` (easy to miss if
warnings aren't surfaced in CI).

This is a stricter cousin of CH006 (floating-task): CH006's task is at least
*scheduled* and can still fail mid-run; here nothing ever starts.

Precision matters a lot here specifically because the sync/async "twin
method" convention (a `def foo` and an `async def foo` on two different
classes, e.g. `Toolkit` vs `AsyncToolkit`) is common in exactly the
codebases this tool targets - a naive whole-file name match flags every
`self.foo()` call against *any* same-named async method anywhere in the
file, sync twin included. Two real false positives found this way while
building this check (agno's `ZepTools`/`ZepAsyncTools.initialize`, and a
`write` call parameter shadowed by an unrelated same-named async closure
hundreds of lines away) are why the matching below is scoped:

- `foo()` (bare name): only matches a module-level `async def foo`, and
  only if `foo` isn't also a parameter of the enclosing function (a
  parameter shadows any outer name with the same spelling).
- `self.foo()` / `cls.foo()`: only matches an `async def foo` defined
  directly in the *same* enclosing class as the call site - not a
  same-named method on an unrelated class elsewhere in the file.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_class, enclosing_function

# Decorators known to leave "calling this returns a coroutine" intact. Any
# other decorator can replace the call's return value entirely - textual's
# `@work` turns an async method into a sync call that schedules a Worker, so
# a bare `self._loader()` there is correct - so an async def carrying one is
# skipped rather than guessed at.
_TRANSPARENT_DECORATORS = frozenset(
    {"staticmethod", "classmethod", "abstractmethod", "override", "final", "wraps"}
)


def _decorator_name(dec: ast.expr) -> str | None:
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        return dec.attr
    return None


class UnawaitedCoroutineCall(Check):
    code = "CH007"
    name = "unawaited-coroutine-call"
    description = "async function called without await/create_task; the coroutine never runs."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        module_level_async: set[str] = set()
        class_async_methods: dict[int, set[str]] = {}

        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not all(_decorator_name(d) in _TRANSPARENT_DECORATORS for d in node.decorator_list):
                continue
            parent = parents.get(id(node))
            if isinstance(parent, ast.Module):
                module_level_async.add(node.name)
            elif isinstance(parent, ast.ClassDef):
                class_async_methods.setdefault(id(parent), set()).add(node.name)

        if not module_level_async and not class_async_methods:
            return []

        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            func = call.func
            called_name = None

            if isinstance(func, ast.Name):
                if func.id in module_level_async and not self._is_shadowed_param(
                    func.id, node, parents
                ):
                    called_name = func.id
            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id in ("self", "cls"):
                    owning_class = enclosing_class(node, parents)
                    if owning_class is not None and func.attr in class_async_methods.get(
                        id(owning_class), set()
                    ):
                        called_name = func.attr

            if called_name is None:
                continue

            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{called_name}(...)` is an async function called without `await` "
                        f"or scheduling; the coroutine is created and immediately discarded, "
                        f"so its body never runs."
                    ),
                )
            )
        return findings

    @staticmethod
    def _is_shadowed_param(name: str, node: ast.AST, parents: dict) -> bool:
        fn = enclosing_function(node, parents)
        if fn is None:
            return False
        args = fn.args
        all_params = (
            args.posonlyargs
            + args.args
            + args.kwonlyargs
            + ([args.vararg] if args.vararg else [])
            + ([args.kwarg] if args.kwarg else [])
        )
        return any(a.arg == name for a in all_params)
