"""CH046 - a set literal with the same value written twice.

A set can only ever hold one of any given value - `{1, 2, 2, 3}`
doesn't error, it just quietly becomes `{1, 2, 3}`, with the repeated
element gone as if it was never written. Verified directly:

    {1, 2, 2, 3}   # {1, 2, 3}

Same story as CH045's dict-literal duplicate key, one syntax over:
almost always a copy-paste that should have changed the value, or a
typo that made two elements collide when they were meant to be
different. Nothing about the syntax hints that an element silently
disappeared - a set literal that's shorter than the number of elements
written looks, at a glance, exactly like one that isn't.

Matches by actual runtime equality (`1`, `1.0`, and `True` really do
collide as the same set element), for simple, hashable, statically
comparable constants - not by resolving names or arbitrary
expressions.
"""

from __future__ import annotations

import ast

from codehound.core import UNRESOLVED, Check, Finding, literal_value


class DuplicateSetValue(Check):
    code = "CH046"
    name = "duplicate-set-value"
    description = "A set literal has the same value twice - the duplicate silently collapses away."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Set):
                continue
            seen: set = set()
            for elt in node.elts:
                comparable = literal_value(elt)
                if comparable is UNRESOLVED:
                    continue
                if comparable in seen:
                    findings.append(
                        Finding(
                            path=path,
                            line=elt.lineno,
                            col=elt.col_offset,
                            code=self.code,
                            message=(
                                "this value already appeared earlier in the same set literal - "
                                "the duplicate silently collapses away rather than raising or "
                                "warning."
                            ),
                        )
                    )
                seen.add(comparable)
        return findings
