"""CH038 - a literal or a known pure function call, used as a bare statement.

`[1, 2, 3]` or `len(x)` on its own line computes a value and discards
it - unlike a bare function call in general (which might do useful
work through a side effect), a container/number/bool/bytes literal has
*no* side effect to run for, and a call to a function this check
specifically knows is pure (`len`, `sorted`, `isinstance`, `str`, …)
doesn't either. In every real shape this catches, the value was almost
certainly meant to be assigned, returned, or asserted, and got left
behind - often by a half-finished edit (a line that used to end in `=
...` or `return `, with only the prefix deleted). Real hits: pydantic's
`_decorators.py` has a bare `isinstance(var_value, ComputedFieldInfo)`
right before the branch that's supposed to depend on it; mlflow's
transformers integration and vllm's benchmark plotting both discard the
result of `all(<generator that validates/runs work per item>)` - `all`
short-circuits on the first falsy result, so if the validator/worker
returns something falsy on success, only the *first* item ever
actually gets validated or run, silently skipping the rest.

This is flake8-bugbear's B018, ported after inspecting its actual
source rather than guessing at scope, with two precision passes its
own source doesn't have - both found by reading real corpus hits, not
guessed in advance:

- **A container literal is only flagged if every element is itself a
  constant** (recursively - a literal nested inside is fine, anything
  else isn't). Bugbear's B018 flags *any* `List`/`Set`/`Dict`/`Tuple`
  unconditionally, which misses that a tuple can hold elements with
  real behavior: HuggingFace `datasets`' `indices.pop(0), tasks.pop(0)`
  is a tuple of two calls, each mutating a list - the tuple itself is
  discarded, but the pops are the point. scikit-learn's `_covtype.py`
  has `X, y` inside `try: ... except NameError:` - deliberately probing
  whether those two names are already bound, exploiting the `NameError`
  a *name* reference raises when it isn't. Neither is "forgot to
  assign, return, or assert" - both compute nothing but still do
  something.
- **A call to a "pure" builtin is only flagged if that name isn't
  shadowed anywhere else in the file.** `set(...)`/`str(...)`/etc. are
  ordinary identifiers, not keywords - `with Progress(...) as set:`
  followed by `set("Building...")` is a real pattern found in
  langgraph's CLI, and it's calling that local status-setter, not the
  builtin type. Checked once per file: any assignment target,
  parameter, `with ... as`, `except ... as`, `def`/`class` name, or
  import alias with that name means it can't be trusted as the real
  builtin here.

One accepted, undetectable-via-AST limitation, same as bugbear's own:
a call to a builtin genuinely in the curated list, used specifically
to probe whether it raises (`try: repr(x) except Exception:` to check
for a broken `__repr__`, the same idiom as the `int(s)` validation case
this check already excludes `int` for) still gets flagged, because
distinguishing "used for its exception" from "result forgotten" needs
tracing the enclosing `try`/`except`, which risks silently suppressing
the exact class of real "forgot to assign" bug this check exists to
catch. Real instances: letta's `otel/tracing.py` (`str(value)` probing
for a broken `__str__`) and scikit-learn's `estimator_checks.py`
(`repr(estimator)` probing for a broken `__repr__`).

Also excluded: the display expression in a function decorated
`@<something>.cell`/`@cell` (marimo's own notebook-cell convention).
marimo always closes a cell function with a `return` naming whatever
it exports to other cells - bare `return` if nothing is exported - so
the *displayed* statement is the last one before that trailing
`return`, not necessarily the literal last statement in the body; both
shapes turned up in the corpus (`1\n    return` and `42\n    return x`
are both real hits, the value and the export existing side by side).
marimo's own `_smoke_tests/` directory alone accounted for over half of
the very first corpus scan's hits before this guard existed. A
different notebook convention - sphinx-gallery's plain
`# %%`-comment-delimited scripts, found in optuna's tutorials - has no
AST-visible marker at all to key off of, so those remain an accepted,
undetected false positive rather than a guessed-at fix.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_PURE_BUILTINS = {
    "all",
    "any",
    "dict",
    "frozenset",
    "isinstance",
    "issubclass",
    "len",
    "max",
    "min",
    "repr",
    "set",
    "sorted",
    "str",
    "tuple",
}


def _is_constant_only(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(_is_constant_only(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(k is not None and _is_constant_only(k) for k in node.keys) and all(
            _is_constant_only(v) for v in node.values
        )
    return False


def _is_useless_value(value: ast.expr, shadowed_names: set[str]) -> bool:
    if isinstance(value, (ast.List, ast.Set, ast.Dict, ast.Tuple)):
        return _is_constant_only(value)
    if isinstance(value, ast.Constant):
        return value.value is None or isinstance(value.value, (int, float, complex, bytes, bool))
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return value.func.id in _PURE_BUILTINS and value.func.id not in shadowed_names
    return False


def _decorator_name(decorator: ast.expr) -> str | None:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def _is_notebook_cell_function(funcdef: ast.FunctionDef | ast.AsyncFunctionDef | None) -> bool:
    if funcdef is None:
        return False
    return any(_decorator_name(d) == "cell" for d in funcdef.decorator_list)


def _is_display_statement(node: ast.Expr, funcdef: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if `node` is the statement whose value a marimo cell
    displays - the last statement of the function body, or the one
    right before a trailing bare `return` (marimo always closes a cell
    with a `return` naming the values it exports to other cells, even
    when the cell's own display value is the expression right before
    it)."""
    body = funcdef.body
    effective_body = body[:-1] if isinstance(body[-1], ast.Return) else body
    return bool(effective_body) and effective_body[-1] is node


def _collect_shadowed_names(tree: ast.AST) -> set[str]:
    """Every name this file binds anywhere - a call to a same-named
    "pure builtin" can't be trusted as the real builtin if the name is
    rebound anywhere in the file."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.alias):
            names.add((node.asname or node.name).split(".")[0])
    return names


class UselessExpressionStatement(Check):
    code = "CH038"
    name = "useless-expression-statement"
    description = "A literal or a call to a known pure function used as a bare statement has no effect and discards its value."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        shadowed_names = _collect_shadowed_names(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not _is_useless_value(node.value, shadowed_names):
                continue
            enclosing = parents.get(id(node))
            if isinstance(enclosing, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_display_statement(node, enclosing):
                if _is_notebook_cell_function(enclosing):
                    continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{type(node.value).__name__}` used as a bare statement has no effect - "
                        f"the value is computed and immediately discarded. Did you forget to "
                        f"assign, return, or assert it?"
                    ),
                )
            )
        return findings
