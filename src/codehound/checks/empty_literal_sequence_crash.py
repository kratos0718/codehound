"""CH074 - a call that's guaranteed to raise on an empty sequence is handed
a literal empty sequence.

Verified directly, each of these raises immediately and unconditionally:

    random.choice([])                        # IndexError: list index out of range
    max([])                                   # ValueError: max() arg is an empty sequence
    min([])                                   # ValueError: min() arg is an empty sequence
    functools.reduce(f, [])                   # TypeError: reduce() of empty sequence with no initial value
    statistics.mean([])                       # StatisticsError: mean requires at least one data point

A literal ``[]``/``()``/``{}``/``set()`` passed straight into one of these
is never going to work - there's no code path where an empty-sequence
constant later becomes non-empty. ``max([], default=0)`` and
``functools.reduce(f, [], initial)`` are the documented, correct ways to
guard exactly this case, so both are excluded whenever the guarding
argument is present.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_EMPTY_TUPLE_OR_LIST = (ast.List, ast.Tuple)


def _is_empty_literal_sequence(node: ast.expr) -> bool:
    if isinstance(node, _EMPTY_TUPLE_OR_LIST):
        return len(node.elts) == 0
    if isinstance(node, ast.Dict):
        return len(node.keys) == 0
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "set":
        return not node.args and not node.keywords
    return False


def _check(node: ast.Call) -> tuple[str, str] | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        base = func.value.id if isinstance(func.value, ast.Name) else None
        if func.attr == "choice" and base == "random" and node.args:
            if _is_empty_literal_sequence(node.args[0]):
                return "random.choice", "IndexError"
        if func.attr == "reduce" and base in ("functools", None) and len(node.args) == 2:
            if _is_empty_literal_sequence(node.args[1]):
                return "functools.reduce", "TypeError"
        if func.attr in ("mean", "median", "mode", "stdev", "pstdev", "variance", "pvariance") and node.args:
            if base == "statistics" and _is_empty_literal_sequence(node.args[0]):
                return f"statistics.{func.attr}", "StatisticsError"
    if isinstance(func, ast.Name) and func.id in ("max", "min") and len(node.args) == 1:
        has_default = any(kw.arg == "default" for kw in node.keywords)
        if not has_default and _is_empty_literal_sequence(node.args[0]):
            return func.id, "ValueError"
    if isinstance(func, ast.Name) and func.id == "reduce" and len(node.args) == 2:
        if _is_empty_literal_sequence(node.args[1]):
            return "reduce", "TypeError"
    return None


class EmptyLiteralSequenceCrash(Check):
    code = "CH074"
    name = "empty-literal-sequence-crash"
    description = "A call that always raises on an empty sequence (random.choice, max/min, reduce, statistics.*) is given a literal empty one."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            result = _check(node)
            if result is None:
                continue
            callee, exc = result
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"{callee}() is called with a literal empty sequence, which always "
                        f"raises {exc} - there's no code path where this constant becomes "
                        f"non-empty."
                    ),
                )
            )
        return findings
