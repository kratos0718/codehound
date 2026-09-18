"""CH010 - A lambda captures a ``for``-loop variable by reference, not value.

Python closures capture *variables*, not their values at creation time.
``[lambda: i for i in range(3)]`` creates three lambdas that all read the
same cell - by the time any of them is called, the loop has finished and
``i`` is ``2`` in all three. The fix is to bind the value as a default
argument (``lambda i=i: i``), which evaluates ``i`` at lambda-creation
time instead of call time.

This only bites when the lambda is called *after* the loop variable has
moved on: stored in a list and used later, returned, handed to a
callback registry. The overwhelmingly common way a lambda appears inside
a loop is the *opposite* of that - passed straight into a higher-order
function that calls it immediately and returns, all within the same
iteration (``sorted(rows, key=lambda r: r[field])``, ``filter(...)``,
``max(..., key=...)``). That shape is completely safe: nothing outlives
the iteration. A real false positive of exactly this kind was found
scanning marimo's table sorter (``sorted(key=lambda row: row[sort_arg.by])``
inside ``for sort_arg in ...``) before this check was scoped correctly.

So this only fires when the lambda is directly *stored* rather than
passed as a callback: the argument to ``.append(...)``/``.add(...)``, the
value of an assignment (`` x = lambda: ...``, `` d[k] = lambda: ...``), or
returned/yielded. A lambda passed as an argument to anything else -
``sorted``, ``filter``, ``map``, a comprehension's own condition - is not
flagged, because nothing has captured it past this iteration.

Comprehensions (`` [lambda: i for i in range(3)] ``) are the one
exception: the ``elt``/``key``/``value`` position *is* inherently the
"produce and store" position, so no extra storage-context check is
needed there.

Same bug, same fix, different syntax: a nested ``def`` inside a ``for``
loop captures the loop variable exactly the same way a lambda does -
flake8-bugbear's B023 covers both shapes under one rule, and this check
now does too. ``def`` is a statement, not an expression, so "is it
stored" means something different: the function's *name* has to show up
later in a storage position (appended, assigned, returned), not the
``def`` itself.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_STORAGE_METHODS = {"append", "add"}


def _references_name_unshadowed(lam: ast.Lambda, name: str) -> bool:
    param_names = {a.arg for a in (lam.args.posonlyargs + lam.args.args + lam.args.kwonlyargs)}
    if lam.args.vararg:
        param_names.add(lam.args.vararg.arg)
    if lam.args.kwarg:
        param_names.add(lam.args.kwarg.arg)
    if name in param_names:
        return False
    for node in ast.walk(lam.body):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
            return True
    return False


def _references_name_in_body(funcdef: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """Like ``_references_name_unshadowed`` but for a ``def``'s own
    parameters and statement body rather than a lambda's params and
    single expression - a same-named parameter shadows the outer loop
    variable exactly like it would for a lambda."""
    args = funcdef.args
    param_names = {a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs)}
    if args.vararg:
        param_names.add(args.vararg.arg)
    if args.kwarg:
        param_names.add(args.kwarg.arg)
    if name in param_names:
        return False
    for stmt in funcdef.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
                return True
    return False


def _name_is_stored(name: str, loop_body: list[ast.stmt], parents: dict) -> bool:
    """True if `name` (a nested def's own name) is later used in a
    storage position anywhere in the loop body: assigned, returned/
    yielded, or passed to `.append()`/`.add()` - same storage shapes
    `_is_stored` recognizes for a lambda, just checked via the Name
    reference's parent instead of the def statement's own parent, since
    a `def` can't be the direct value of an assignment the way a lambda
    expression can."""
    for stmt in loop_body:
        for node in ast.walk(stmt):
            if not (isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load)):
                continue
            parent = parents.get(id(node))
            if isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node:
                return True
            if isinstance(parent, (ast.Return, ast.Yield)) and parent.value is node:
                return True
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Attribute)
                and parent.func.attr in _STORAGE_METHODS
                and node in parent.args
            ):
                return True
    return False


def _is_stored(lam: ast.Lambda, parents: dict) -> bool:
    """True only if the lambda is directly stored somewhere that outlives
    this loop iteration - not merely passed as a callback argument to a
    function (sorted/filter/map/...) that consumes it on the spot."""
    parent = parents.get(id(lam))
    if isinstance(parent, (ast.Assign, ast.AnnAssign)):
        return True
    if isinstance(parent, (ast.Return, ast.Yield)):
        return True
    if (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Attribute)
        and parent.func.attr in _STORAGE_METHODS
        and lam in parent.args
    ):
        return True
    return False


class LoopClosureCapture(Check):
    code = "CH010"
    name = "loop-closure-capture"
    description = "Lambda captures a for-loop variable by reference; all instances see the final value."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        seen: set[int] = set()

        for loop in ast.walk(tree):
            targets: list[str] = []
            body_nodes: list[ast.AST] = []
            require_storage = False
            if isinstance(loop, ast.For) and isinstance(loop.target, ast.Name):
                targets = [loop.target.id]
                body_nodes = loop.body
                require_storage = True
            elif isinstance(loop, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
                gens = [g for g in loop.generators if isinstance(g.target, ast.Name)]
                targets = [g.target.id for g in gens]
                body_nodes = [loop.elt] if not isinstance(loop, ast.DictComp) else [loop.key, loop.value]
            else:
                continue

            for container in body_nodes:
                for node in ast.walk(container):
                    if not isinstance(node, ast.Lambda) or id(node) in seen:
                        continue
                    if require_storage and not _is_stored(node, parents):
                        continue
                    for var in targets:
                        if _references_name_unshadowed(node, var):
                            seen.add(id(node))
                            findings.append(
                                Finding(
                                    path=path,
                                    line=node.lineno,
                                    col=node.col_offset,
                                    code=self.code,
                                    message=(
                                        f"lambda captures loop variable `{var}` by reference; if "
                                        f"called after the loop moves on, every instance sees the "
                                        f"same final value. Bind it explicitly: `lambda {var}={var}: ...`."
                                    ),
                                )
                            )
                            break

            # Same bug, `def` instead of `lambda`: a nested function
            # defined directly in a `for` loop's body, capturing the loop
            # variable, whose *name* (not the def itself) is later stored
            # somewhere that outlives this iteration.
            if isinstance(loop, ast.For) and isinstance(loop.target, ast.Name):
                var = loop.target.id
                for stmt in loop.body:
                    if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if id(stmt) in seen:
                        continue
                    if not _references_name_in_body(stmt, var):
                        continue
                    if not _name_is_stored(stmt.name, loop.body, parents):
                        continue
                    seen.add(id(stmt))
                    findings.append(
                        Finding(
                            path=path,
                            line=stmt.lineno,
                            col=stmt.col_offset,
                            code=self.code,
                            message=(
                                f"`{stmt.name}` captures loop variable `{var}` by reference; if "
                                f"called after the loop moves on, every instance sees the same "
                                f"final value. Bind it explicitly with a default argument, e.g. "
                                f"`def {stmt.name}({var}={var}):`."
                            ),
                        )
                    )
        return findings
