"""CH043 - comparing against ``float('nan')`` with ``==``/``!=`` is always the same answer.

IEEE 754 defines NaN as unequal to everything, including itself -
`float('nan') == float('nan')` is `False`, and so is comparing any
value, NaN or not, against a NaN literal with `==`. Verified directly:

    n = float('nan')
    n == n            # False
    n == float('nan') # False
    math.nan == 5     # False

`x == float('nan')` (or `x != float('nan')`) is not a bug in the sense
of crashing - it's a comparison that always evaluates to the same
constant regardless of `x`, silently. The idiomatic, correct way to
check for NaN is `math.isnan(x)` (or the self-comparison idiom
`x != x`, which relies on the exact same property this check flags as
a mistake when it's a literal on the other side instead).

Flags `==`/`!=` where either side of the comparison is `float('nan')`,
`math.nan`, or `numpy.nan`/`np.nan`.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_NAN_ATTRIBUTES = {("math", "nan"), ("numpy", "nan"), ("np", "nan")}


def _is_nan_literal(node: ast.expr) -> bool:
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "float"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.strip().lower() == "nan"
    ):
        return True
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return (node.value.id, node.attr) in _NAN_ATTRIBUTES
    return False


class NanEqualityComparison(Check):
    code = "CH043"
    name = "nan-equality-comparison"
    description = "== or != against a NaN literal always evaluates the same way, regardless of the other operand; use math.isnan()."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            for left, op, right in zip(operands, node.ops, operands[1:]):
                if not isinstance(op, (ast.Eq, ast.NotEq)):
                    continue
                if not (_is_nan_literal(left) or _is_nan_literal(right)):
                    continue
                op_text = "!=" if isinstance(op, ast.NotEq) else "=="
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{op_text}` against a NaN literal is always "
                            f"{'True' if op_text == '!=' else 'False'} - NaN compares unequal to "
                            f"everything, including itself. Use `math.isnan(...)` instead."
                        ),
                    )
                )
        return findings
