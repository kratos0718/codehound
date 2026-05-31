"""CH003 - Deprecated ``datetime.utcnow()`` / ``datetime.utcfromtimestamp()``.

These return a *naive* datetime that silently claims to be local time, a
long-standing footgun. They are deprecated since Python 3.12 and slated for
removal. Replacement: ``datetime.now(timezone.utc)`` (or, for a naive-UTC
drop-in, ``datetime.now(timezone.utc).replace(tzinfo=None)``).

Real-world: fixed across crewAI's memory subsystem (9 call sites, 4 files).
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_DEPRECATED = {"utcnow", "utcfromtimestamp"}


class DeprecatedDatetimeUtcnow(Check):
    code = "CH003"
    name = "deprecated-datetime-utcnow"
    description = "datetime.utcnow()/utcfromtimestamp() are deprecated and return naive datetimes."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in _DEPRECATED:
                continue
            # value should be `datetime` (Name) or `<something>.datetime` (Attribute)
            value = func.value
            target_ok = (isinstance(value, ast.Name) and value.id == "datetime") or (
                isinstance(value, ast.Attribute) and value.attr == "datetime"
            )
            if not target_ok:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`datetime.{func.attr}()` is deprecated; use "
                        f"`datetime.now(timezone.utc)`."
                    ),
                )
            )
        return findings
