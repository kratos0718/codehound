"""CH002 - Mutable default argument (Ruff B006 / flake8-bugbear).

``def f(x=[])`` evaluates the default exactly once, at definition time, so the
*same* list/dict/set is shared across every call. Mutating it leaks state
between calls - a classic, subtle source of bugs. Fix: default to ``None`` and
build the container inside the body.

Real-world: fixed across agno's toolkits and mem0's proxy/embedder configs.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_MUTABLE_FACTORIES = {"list", "dict", "set", "Counter", "defaultdict", "OrderedDict", "deque"}


def _is_mutable_default(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in _MUTABLE_FACTORIES
    return False


class MutableDefaultArgument(Check):
    code = "CH002"
    name = "mutable-default-argument"
    description = "Mutable default argument is shared across all calls to the function."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
            for default in defaults:
                if _is_mutable_default(default):
                    findings.append(
                        Finding(
                            path=path,
                            line=default.lineno,
                            col=default.col_offset,
                            code=self.code,
                            message=(
                                f"Mutable default in `{node.name}` is shared across calls; "
                                f"use `None` and create the value inside the body."
                            ),
                        )
                    )
        return findings
