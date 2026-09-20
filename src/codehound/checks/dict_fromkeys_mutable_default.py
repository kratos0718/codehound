"""CH065 - ``dict.fromkeys(keys, mutable_value)`` gives every key the
*same* mutable object, not independent copies.

Verified directly: ``d = dict.fromkeys(['a', 'b'], []); d['a'].append(1)``
leaves ``d['b']`` as ``[1]`` too - `d['a'] is d['b']` is `True`.
``fromkeys`` assigns the exact same value object to every key rather than
copying it, the same root cause as a mutable default argument (CH002) or
a mutable class attribute (CH026), one call away. There is no legitimate
reading of this shape - a comprehension (``{k: [] for k in keys}``) is
what actually gives each key its own object.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_mutable_value(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set")


class DictFromkeysMutableDefault(Check):
    code = "CH065"
    name = "dict-fromkeys-mutable-default"
    description = "dict.fromkeys(keys, value) gives every key the same mutable object, not independent copies."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "fromkeys"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "dict"
            ):
                continue
            if len(node.args) < 2 or not _is_mutable_value(node.args[1]):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "`dict.fromkeys(keys, value)` assigns this exact value object to "
                        "every key, not a copy per key - mutating one key's value is visible "
                        "through all of them. Use a comprehension instead: "
                        "`{k: ... for k in keys}`."
                    ),
                )
            )
        return findings
