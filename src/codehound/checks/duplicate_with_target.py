"""CH055 - two context managers in the same ``with`` statement bound to the
same ``as`` name.

``with open(a) as f, open(b) as f:`` rebinds ``f`` to the second file the
moment the second ``withitem`` runs - nothing raises, it's an entirely
ordinary name rebinding as far as Python is concerned. But the first
context manager is still open at that point, and the only name that ever
pointed at it has just been overwritten, so whatever cleanup the first
``with`` would have let the caller do explicitly (closing it, reading it)
can no longer happen through that name at all. There is no reading of one
``with`` statement giving two different resources the same bound name on
purpose - if two resources really are meant to share a name, they aren't
both needed at once, which is what two separate ``with`` statements are for.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class DuplicateWithTarget(Check):
    code = "CH055"
    name = "duplicate-with-target"
    description = "The same `as` name is bound twice in one `with` statement, shadowing the first context manager."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            seen: dict[str, ast.withitem] = {}
            for item in node.items:
                if not isinstance(item.optional_vars, ast.Name):
                    continue
                name = item.optional_vars.id
                if name in seen:
                    findings.append(
                        Finding(
                            path=path,
                            line=item.context_expr.lineno,
                            col=item.context_expr.col_offset,
                            code=self.code,
                            message=(
                                f"`as {name}` is bound twice in this `with` statement - the "
                                f"second context manager overwrites the name before the first "
                                f"one is ever used, leaving it reachable only until this line."
                            ),
                        )
                    )
                else:
                    seen[name] = item
        return findings
