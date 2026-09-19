"""CH042 - the same exception type listed in more than one place in a ``try``.

Python matches `except` clauses top to bottom and stops at the first
one whose type matches - once one handler names an exception type,
every later handler naming that *same* type (whether as its own clause
or a second time inside the same clause's tuple) can never run.
Verified directly: `except ValueError: ... except ValueError: ...`
doesn't raise anything - the second handler is simply dead code,
silently unreachable.

This is flake8-bugbear's B025. Matches by literal name text, not
resolved type identity - the same "no type inference" tradeoff every
AST-only check in this project accepts (an aliased import,
`from x import ValueError as VE`, could in principle name the same
type twice under different spellings and slip past this).
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _handler_names(handler: ast.ExceptHandler) -> list[ast.Name]:
    exc_type = handler.type
    if isinstance(exc_type, ast.Tuple):
        return [elt for elt in exc_type.elts if isinstance(elt, ast.Name)]
    if isinstance(exc_type, ast.Name):
        return [exc_type]
    return []


class DuplicateExceptHandler(Check):
    code = "CH042"
    name = "duplicate-except-handler"
    description = "The same exception type appears in more than one except clause of the same try - the later one is unreachable."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            seen: set[str] = set()
            for handler in node.handlers:
                for name_node in _handler_names(handler):
                    if name_node.id in seen:
                        findings.append(
                            Finding(
                                path=path,
                                line=name_node.lineno,
                                col=name_node.col_offset,
                                code=self.code,
                                message=(
                                    f"`{name_node.id}` is already caught by an earlier except "
                                    f"clause in this try - this one is unreachable."
                                ),
                            )
                        )
                    seen.add(name_node.id)
        return findings
