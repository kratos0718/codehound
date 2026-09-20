"""CH092 - ``Path.write_text()`` given bytes, or ``Path.write_bytes()``
given a string.

Verified directly:

    Path(f).write_text(b"hello")           # (via .encode())
    # TypeError: data must be str, not bytes

    Path(f).write_bytes("hello")
    # TypeError: memoryview: a bytes-like object is required, not 'str'

Unlike `open(f, mode)`, which at least fails at open time if the mode
doesn't match, `write_text`/`write_bytes` commit to one type each and
always raise if handed the other - there's no implicit encode/decode.

Only fires on two provably-typed shapes: `.write_text(...)` given a
bytes literal or an `.encode(...)` call's result, and `.write_bytes(...)`
given a string literal or a `.decode(...)` call's result - the same
"encode produces bytes, decode produces str" reasoning CH073 uses for
`str()` on bytes.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_bytes_shaped(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, bytes):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "encode"


def _is_str_shaped(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "decode"


class PathWriteTypeMismatch(Check):
    code = "CH092"
    name = "path-write-type-mismatch"
    description = "Path.write_text() given bytes, or write_bytes() given a str - always raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if len(node.args) != 1:
                continue
            arg = node.args[0]
            if node.func.attr == "write_text" and _is_bytes_shaped(arg):
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message="write_text() is given bytes - it requires str, and never encodes/decodes implicitly. Raises TypeError.",
                    )
                )
            elif node.func.attr == "write_bytes" and _is_str_shaped(arg):
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message="write_bytes() is given a str - it requires bytes, and never encodes/decodes implicitly. Raises TypeError.",
                    )
                )
        return findings
