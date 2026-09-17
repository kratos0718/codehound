"""CH019 - ``inspect.getargspec`` was removed in Python 3.11.

Deprecated since 3.0, kept alive for over a decade, and finally removed in
3.11 - `inspect.getargspec(...)` now raises `AttributeError` immediately.
`inspect.signature(...)` is the modern replacement (`getfullargspec` also
still exists, for code that specifically needs its exact return shape).
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class RemovedGetargspec(Check):
    code = "CH019"
    name = "removed-getargspec"
    description = "inspect.getargspec was removed in Python 3.11; use inspect.signature."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "inspect":
                for alias in node.names:
                    if alias.name == "getargspec":
                        findings.append(
                            Finding(
                                path=path,
                                line=node.lineno,
                                col=node.col_offset,
                                code=self.code,
                                message=(
                                    "`from inspect import getargspec` - removed in Python 3.11; "
                                    "use `inspect.signature(...)`."
                                ),
                            )
                        )
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getargspec"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "inspect"
            ):
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            "`inspect.getargspec(...)` - removed in Python 3.11; use "
                            "`inspect.signature(...)`."
                        ),
                    )
                )
        return findings
