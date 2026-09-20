"""CH073 - ``str()`` called directly on bytes instead of ``.decode()``.

Verified directly:

    data = b"hello"
    str(data)          # "b'hello'"  - the repr, not the text
    data.decode()       # "hello"

``str(some_bytes)`` doesn't decode anything - with a single argument it
just falls back to ``repr()``-like formatting, so the ``b'...'`` wrapper
and any escape sequences end up baked into the "text" as literal
characters. This is the classic Python 2 -> 3 porting bug: ``str(x)`` used
to decode bytes using the default encoding in Python 2, and silently
stopped doing that in Python 3.

Only fires on two provably-bytes shapes: a bytes literal (``str(b"...")``),
and the direct result of ``.encode(...)`` (``str(x.encode())``) - wrapping
an encode() call in str() right back is never intentional. The two-argument
form, ``str(data, "utf-8")``, is the *correct* way to decode bytes and is
never flagged.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_bytes_literal(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, bytes)


def _is_encode_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "encode"


class StrOnBytes(Check):
    code = "CH073"
    name = "str-on-bytes"
    description = "str() on a bytes literal or .encode() result produces the b'...' repr, not decoded text."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not (isinstance(node.func, ast.Name) and node.func.id == "str"):
                continue
            if len(node.args) != 1 or node.keywords:
                continue
            arg = node.args[0]
            if _is_bytes_literal(arg):
                shape = "a bytes literal"
            elif _is_encode_call(arg):
                shape = "the result of .encode()"
            else:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"str() called on {shape} produces the \"b'...'\" repr, not decoded "
                        f"text - use .decode() instead, or str(data, encoding) if a specific "
                        f"encoding is needed."
                    ),
                )
            )
        return findings
