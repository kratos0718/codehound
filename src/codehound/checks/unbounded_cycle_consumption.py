"""CH063 - ``itertools.cycle(...)`` passed directly to something that tries
to consume it in full.

``itertools.cycle`` is infinite by definition - it repeats its input
forever. ``list(itertools.cycle(x))``, ``sum(itertools.cycle(x))``, and
similar hang forever, not raise, since there is no way for a function that
consumes its whole argument to ever reach the end of something that never
ends. There is no legitimate reading of this shape: anyone who wants a
bounded number of repetitions reaches for ``itertools.islice(cycle(x), n)``
instead, which this check does not flag.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_TERMINAL_FUNCS = {"list", "tuple", "set", "sorted", "sum", "max", "min", "frozenset"}


def _is_cycle_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "cycle"
    return isinstance(func, ast.Attribute) and func.attr == "cycle"


class UnboundedCycleConsumption(Check):
    code = "CH063"
    name = "unbounded-cycle-consumption"
    description = "itertools.cycle(...) passed directly to a function that tries to consume it in full."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _TERMINAL_FUNCS
                and len(node.args) >= 1
                and _is_cycle_call(node.args[0])
            ):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`itertools.cycle(...)` is infinite - `{node.func.id}(cycle(...))` "
                        f"hangs forever trying to consume it in full. Use "
                        f"`itertools.islice(cycle(...), n)` for a bounded number of repeats."
                    ),
                )
            )
        return findings
