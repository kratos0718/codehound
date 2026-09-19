"""CH048 - ``assert (condition, "message")`` is always true - it's a non-empty tuple.

`assert` takes an expression and an optional message, separated by a
comma - `assert x, "message"`. Wrapping both in parentheses,
`assert (x, "message")`, doesn't group them into that same
expression-plus-message form; it makes the *whole thing* a single
2-element tuple, and a non-empty tuple is always truthy, regardless of
what `x` actually is. CPython's own compiler already emits
`SyntaxWarning: assertion is always true, perhaps remove parentheses?`
for exactly this - verified directly:

    def check(x):
        assert (x == 5, "x should be 5")
        return "passed"

    check(999)   # "passed" - the assertion can never fail, for any x

This is pyflakes' F631. Included here even though CPython's own
compiler already warns about it, because a `SyntaxWarning` is easy to
miss - it doesn't fail a test suite, doesn't show up in most CI output
by default, and this exact typo (adding parens to what looks like the
Python 2 `assert (cond, msg)` call-shaped syntax) silently turns a real
assertion into a no-op with zero indication anything is wrong at the
call site.

Flags any `assert` whose test expression is a non-empty tuple literal.
`assert ()` (an empty tuple, always false) is a different, much rarer
mistake with the opposite effect - not flagged here, since it fails
loudly and immediately rather than silently doing nothing.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class AssertOnTuple(Check):
    code = "CH048"
    name = "assert-on-tuple"
    description = "assert (x, 'message') is always true - it's a non-empty tuple, not a condition-plus-message."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assert):
                continue
            if not (isinstance(node.test, ast.Tuple) and len(node.test.elts) > 0):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "asserting a non-empty tuple is always true, regardless of its "
                        "contents - remove the parentheses (`assert x, \"message\"`) unless "
                        "the tuple itself is really the intended check."
                    ),
                )
            )
        return findings
