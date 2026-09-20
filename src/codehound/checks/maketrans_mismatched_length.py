"""CH099 - ``str.maketrans(a, b)`` with two literal strings of different
lengths.

Verified directly:

    str.maketrans('abc', 'de')
    # ValueError: the first two maketrans arguments must have equal length

`maketrans`'s two-argument form builds a translation table by pairing up
`a[i]` with `b[i]` for every index - there's no meaningful way to build
that table if the strings aren't the same length, so Python refuses
outright rather than guessing (silently truncating or padding).

Only fires when both arguments are string literals with a statically
different length - both sides fully known, zero ambiguity.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class MaketransMismatchedLength(Check):
    code = "CH099"
    name = "maketrans-mismatched-length"
    description = "str.maketrans(a, b) with two literal strings of different lengths always raises ValueError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) != 2:
                continue
            func = node.func
            is_maketrans = (isinstance(func, ast.Attribute) and func.attr == "maketrans") or (
                isinstance(func, ast.Name) and func.id == "maketrans"
            )
            if not is_maketrans:
                continue
            a, b = node.args
            if not (
                isinstance(a, ast.Constant)
                and isinstance(a.value, str)
                and isinstance(b, ast.Constant)
                and isinstance(b.value, str)
            ):
                continue
            if len(a.value) == len(b.value):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"maketrans()'s two string arguments have different lengths "
                        f"({len(a.value)} vs {len(b.value)}) - the two-argument form pairs "
                        f"them up by index, so this always raises ValueError."
                    ),
                )
            )
        return findings
