"""CH041 - ``contextlib.suppress()`` with no exception types suppresses nothing.

`contextlib.suppress(*exceptions)` only catches the exception types
listed - with zero arguments, there's nothing in that list, so it
catches nothing at all. Verified directly:

    with contextlib.suppress():
        raise ValueError("boom")
    # ValueError propagates - the with-block did nothing

The exact same shape as CH035 (`except ():`), one layer of API away:
both look like they're suppressing something, and both suppress
nothing, because both hand an empty set of exception types to a
mechanism that matches against exactly that set. This is flake8-bugbear's
B022.

Only flags the zero-argument call. `suppress()` is trusted as the real
`contextlib.suppress` - not some unrelated same-named function - only
when either the qualified form (`contextlib.suppress`) is used, or the
bare name was actually imported via `from contextlib import suppress`,
the same "don't trust a bare name without seeing where it came from"
discipline CH018/CH022/CH028 already use.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _imports_bare_suppress(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "contextlib":
            for alias in node.names:
                if alias.name == "suppress":
                    return True
    return False


def _is_empty_suppress_call(call: ast.Call, bare_suppress_trusted: bool) -> bool:
    if call.args or call.keywords:
        return False
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "suppress" and isinstance(func.value, ast.Name) and func.value.id == "contextlib":
        return True
    if isinstance(func, ast.Name) and func.id == "suppress" and bare_suppress_trusted:
        return True
    return False


class SuppressEmpty(Check):
    code = "CH041"
    name = "suppress-empty"
    description = "contextlib.suppress() with no arguments suppresses nothing - every exception still propagates."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        bare_suppress_trusted = _imports_bare_suppress(tree)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            for item in node.items:
                if not isinstance(item.context_expr, ast.Call):
                    continue
                if not _is_empty_suppress_call(item.context_expr, bare_suppress_trusted):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=item.context_expr.lineno,
                        col=item.context_expr.col_offset,
                        code=self.code,
                        message=(
                            "`suppress()` with no exception types catches nothing - every "
                            "exception raised in this block still propagates. Pass the "
                            "exception type(s) you meant to suppress."
                        ),
                    )
                )
        return findings
