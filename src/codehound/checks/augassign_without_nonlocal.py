"""CH044 - augmented assignment to an enclosing-scope name, missing ``nonlocal``.

Python decides whether a name is local to a function at *compile* time,
from the mere presence of an assignment target anywhere in the
function body - not from execution order. `count += 1` is exactly
`count = count + 1`: the assignment target makes `count` local to the
*whole* function, so reading `count` on the right-hand side reads that
new local variable, which has no value yet. Verified directly:

    def outer():
        count = 0
        def inc():
            count += 1
            return count
        return inc()

    outer()  # UnboundLocalError: cannot access local variable 'count'
             # where it is not associated with a value

This crashes on the very first call, every time - not a maybe. The fix
is a `nonlocal count` declaration, which tells the compiler `count`
refers to the enclosing scope's variable instead of creating a new
local one.

Flags an `AugAssign` whose target is a bare name, inside a function
that itself is nested inside another function (module-level and
class-body-level functions can't have this specific bug - there's no
enclosing function scope for `nonlocal` to reach), where that name
isn't a parameter, isn't declared `nonlocal`/`global` anywhere in the
function, and has no *other* binding anywhere else in the same
function's own scope (not counting further-nested functions/classes,
which are separate scopes). That last condition is what tells apart
the guaranteed crash from `count = 5` followed by `count += 1` in the
same function - there, `count` really is a fresh local the whole way
through, shadowing the outer one silently instead of crashing.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


def _param_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    names = {a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs)}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _declares_nonlocal_or_global(func: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, (ast.Nonlocal, ast.Global)) and name in node.names:
            return True
    return False


def _count_local_bindings(node: ast.AST, name: str) -> int:
    count = 0
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store) and child.id == name:
            count += 1
        count += _count_local_bindings(child, name)
    return count


class AugassignWithoutNonlocal(Check):
    code = "CH044"
    name = "augassign-without-nonlocal"
    description = "Augmented assignment to an enclosing-scope name without `nonlocal` crashes with UnboundLocalError on first call."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name)):
                continue
            name = node.target.id
            func = enclosing_function(node, parents)
            if func is None or enclosing_function(func, parents) is None:
                continue
            if name in _param_names(func):
                continue
            if _declares_nonlocal_or_global(func, name):
                continue
            if _count_local_bindings(func, name) != 1:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"augmented assignment to `{name}` reads it before assigning to it - "
                        f"since it's assigned here, it's local to `{func.name}` for the whole "
                        f"function, so this crashes with UnboundLocalError on the very first "
                        f"call. Add `nonlocal {name}` if you meant the enclosing scope's "
                        f"variable."
                    ),
                )
            )
        return findings
