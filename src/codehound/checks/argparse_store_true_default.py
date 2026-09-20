"""CH058 - ``action="store_true"`` combined with ``default=True`` makes the
flag permanently on.

``store_true`` sets the value to ``True`` when the flag is present, and to
``default`` when it's absent - that is its whole contract. Setting
``default=True`` means the value is ``True`` in both cases: present or
absent, there is no way for a user to pass this flag and get anything but
``True`` back. Whatever the flag is supposed to let someone opt into, they
can no longer opt out of it; the flag still parses, still shows up in
``--help``, and does nothing. The same thing happens in reverse for
``store_false`` with ``default=False``.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _kwarg_value(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _is_bool(node: ast.expr | None, value: bool) -> bool:
    return isinstance(node, ast.Constant) and node.value is value


class ArgparseStoreTrueDefault(Check):
    code = "CH058"
    name = "argparse-store-true-default"
    description = "action='store_true'/'store_false' paired with a default that matches the flag's own effect."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"
            ):
                continue
            action = _kwarg_value(node, "action")
            default = _kwarg_value(node, "default")
            if default is None or not isinstance(action, ast.Constant):
                continue
            if action.value == "store_true" and _is_bool(default, True):
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            "action='store_true' with default=True means the value is True "
                            "whether or not the flag is passed - there is no way to opt out."
                        ),
                    )
                )
            elif action.value == "store_false" and _is_bool(default, False):
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            "action='store_false' with default=False means the value is False "
                            "whether or not the flag is passed - there is no way to opt in."
                        ),
                    )
                )
        return findings
