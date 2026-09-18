"""CH035 - ``except ():`` catches nothing at all.

`isinstance(exc, ())` is always `False` - an empty tuple has nothing
to match against - so `except ():` is a handler that can *never* run.
Verified directly:

    try:
        raise ValueError("boom")
    except ():
        print("caught")   # never printed
    # ValueError propagates past the handler, as if it wasn't there

This is flake8-bugbear's B029. It's easy to write by accident - a
`(SomeError,)` tuple that gets refactored down to nothing (a variable
that used to hold exception types now holds an empty list/tuple,
or an `except (E1, E2):` where both names got deleted during a merge)
silently turns into dead code with no error, no warning, and a handler
that reads as if it's protecting something it no longer protects.

Zero configuration, zero false-positive risk: an empty tuple can never
match any exception, so there's no reading of `except ():` where it's
doing useful work.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class EmptyExceptTuple(Check):
    code = "CH035"
    name = "empty-except-tuple"
    description = "except () catches nothing - an empty exception tuple can never match, so the handler is dead code."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not (isinstance(node.type, ast.Tuple) and len(node.type.elts) == 0):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "`except ():` can never match any exception - an empty tuple has "
                        "nothing to catch, so this handler is dead code and every exception "
                        "still propagates past it."
                    ),
                )
            )
        return findings
