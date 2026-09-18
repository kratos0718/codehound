"""CH037 - a comparison used as a bare statement, its result discarded.

`x == 5` as its own statement computes a boolean and immediately
throws it away - the exact same "result silently dropped" shape CH006
(discarded task) and CH013 (discarded future) exist to catch, just for
the plainest possible expression instead of an async call. There's no
legitimate reason to write a bare comparison for its result alone
(`==`/`!=`/`<`/`is`/`in`/... never have a documented, intended side
effect), so in every real case this found while building it, it was
one of two typos: `==` where `=` (assignment) was meant, or a
comparison that should have been wrapped in `assert`.

This is flake8-bugbear's B015, verified against its actual source
rather than assumed: it fires whenever an `ast.Compare` node's
immediate parent is an `ast.Expr` statement - exactly what this check
does too.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class PointlessComparisonStatement(Check):
    code = "CH037"
    name = "pointless-comparison-statement"
    description = "A comparison used as a bare statement discards its result - likely a typo for `=` or a missing `assert`."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Compare):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "comparison used as a bare statement - the result is computed and "
                        "immediately discarded. Likely a typo for `=` (assignment) or a "
                        "comparison that should be wrapped in `assert`."
                    ),
                )
            )
        return findings
