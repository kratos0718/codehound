"""CH056 - joining a ``pathlib.Path`` with a string literal that looks
absolute silently discards everything on the left.

Verified directly: ``Path("/etc/myapp/config") / "/passwd"`` is
``Path("/passwd")`` - the left side vanishes completely, no error, no
warning. ``Path.__truediv__`` treats an operand starting with ``/`` as
already absolute and replaces the accumulated path outright rather than
appending to it, the same rule ``os.path.join`` has always had. A hardcoded
string literal is never *meant* to be absolute here - if it were genuinely
meant to replace the base, the base wouldn't have been built in the first
place - so this only fires on a literal, leaving a variable (which really
might come from untrusted input, the more dangerous version of this same
mistake) undetectable without type inference this check doesn't have.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _looks_like_path_join(node: ast.BinOp) -> bool:
    left = node.left
    if isinstance(left, ast.Call) and isinstance(left.func, (ast.Name, ast.Attribute)):
        func_name = left.func.id if isinstance(left.func, ast.Name) else left.func.attr
        if func_name in ("Path", "PurePath", "PosixPath", "PurePosixPath"):
            return True
    # a chained join, e.g. (Path(x) / "a") / "/b"
    return isinstance(left, ast.BinOp) and isinstance(left.op, ast.Div) and _looks_like_path_join(left)


class PathAbsoluteLiteralJoin(Check):
    code = "CH056"
    name = "path-absolute-literal-join"
    description = "Joining a Path with a string literal starting with '/' discards everything joined so far."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Div):
                continue
            right = node.right
            if not (isinstance(right, ast.Constant) and isinstance(right.value, str) and right.value.startswith("/")):
                continue
            if not _looks_like_path_join(node):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=right.lineno,
                    col=right.col_offset,
                    code=self.code,
                    message=(
                        f"`{right.value!r}` starts with '/', so joining it onto a Path with `/` "
                        f"replaces everything built so far instead of appending to it - "
                        f"`Path('/a') / '/b'` is `Path('/b')`, not `Path('/a/b')`."
                    ),
                )
            )
        return findings
