"""CH090 - ``__exit__``/``__aexit__`` unconditionally returns ``True``,
suppressing every exception the ``with`` block ever raises.

Verified directly:

    class CM:
        def __enter__(self): return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            print("cleanup")
            return True
    with CM():
        raise ValueError("boom")
    # nothing printed, nothing raised - the ValueError is gone

Returning a truthy value from ``__exit__`` tells the ``with`` statement
the exception was handled and should not propagate - the *entire*
mechanism `with` blocks use to report failure. Doing that unconditionally,
with no branch that ever inspects `exc_type`, silently swallows every
exception any code in the block ever raises, not just ones related to
the resource being managed.

Only fires when every `return` in the method returns the literal `True`
(no other return value exists anywhere in the function), and the
exception-type parameter is never referenced in any comparison - so
there's no branch anywhere that's actually deciding based on what went
wrong. A conditional `return True` (e.g. only for a specific caught
type) is a normal, correct pattern and is never touched by this check.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_EXIT_METHODS = {"__exit__", "__aexit__"}


def _is_literal_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _references_name_in_compare(node: ast.AST, name: str) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Compare):
            operands = [n.left, *n.comparators]
            if any(isinstance(o, ast.Name) and o.id == name for o in operands):
                return True
    return False


class ExitReturnsTrueUnconditionally(Check):
    code = "CH090"
    name = "exit-returns-true-unconditionally"
    description = "__exit__/__aexit__ always returns True with no branch on the exception type - silently suppresses every exception."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for method in cls.body:
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if method.name not in _EXIT_METHODS:
                    continue
                params = method.args.args
                if len(params) < 2:
                    continue
                exc_type_param = params[1].arg
                returns = [n for n in ast.walk(method) if isinstance(n, ast.Return)]
                if not returns or not all(_is_literal_true(r.value) for r in returns):
                    continue
                if _references_name_in_compare(method, exc_type_param):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=method.lineno,
                        col=method.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}.{method.name}` always returns True with no branch on "
                            f"`{exc_type_param}` - every exception raised inside the with block "
                            f"is silently suppressed, not just ones this context manager is "
                            f"meant to handle."
                        ),
                    )
                )
        return findings
