"""CH089 - ``str.join()`` given a list of bytes, or ``bytes.join()`` given
a list of strings.

Verified directly:

    ", ".join([b"a", b"b"])
    # TypeError: sequence item 0: expected str instance, bytes found

    b", ".join(["a", "b"])
    # TypeError: sequence item 0: expected a bytes-like object, str found

``join()``'s separator and its elements have to be the same str/bytes
family - there's no implicit conversion either direction, unlike most
other places str and bytes get silently coerced against each other.

Only fires when the separator is a literal (`"...".join(...)` or
`b"...".join(...)`) and the argument is a list/tuple literal whose
elements are *all* constants of the opposite family - both sides
provably known, zero ambiguity.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _elements(node: ast.expr) -> list[ast.expr] | None:
    if isinstance(node, (ast.List, ast.Tuple)):
        return node.elts
    return None


class BytesStrJoinMismatch(Check):
    code = "CH089"
    name = "bytes-str-join-mismatch"
    description = "str.join() given a list of bytes (or bytes.join() given a list of str) always raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "join" or len(node.args) != 1:
                continue
            sep = node.func.value
            if not (isinstance(sep, ast.Constant) and isinstance(sep.value, (str, bytes))):
                continue
            elements = _elements(node.args[0])
            if not elements:
                continue
            sep_is_bytes = isinstance(sep.value, bytes)
            wanted_wrong_type = str if sep_is_bytes else bytes
            if not all(isinstance(e, ast.Constant) and isinstance(e.value, wanted_wrong_type) for e in elements):
                continue
            sep_kind = "bytes" if sep_is_bytes else "str"
            elt_kind = "str" if sep_is_bytes else "bytes"
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"a {sep_kind} separator's .join() is given a list of {elt_kind} elements - "
                        f"join() never mixes the two families, this raises TypeError on the first element."
                    ),
                )
            )
        return findings
