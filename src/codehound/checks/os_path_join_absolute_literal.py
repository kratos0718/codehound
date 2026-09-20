"""CH066 - ``os.path.join(base, '/literal', ...)`` discards ``base`` and
everything before the absolute component.

Verified directly: ``os.path.join('/etc/myapp', '/passwd')`` is
``/passwd``, not ``/etc/myapp/passwd`` - `os.path.join` treats any
component starting with the path separator as an already-absolute path
and restarts from it, the same rule ``pathlib.Path.__truediv__`` follows
(see CH056). A hardcoded string literal is never *meant* to be absolute
here - only a variable that might come from untrusted input would make
this genuinely dangerous, and that shape can't be told apart from an
ordinary relative-path variable without type inference this check
doesn't have, so only a literal is flagged.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_os_path_join(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "join":
        return False
    value = func.value
    if isinstance(value, ast.Name):
        return value.id == "path"  # `from os import path` / `import os.path as path`
    if isinstance(value, ast.Attribute):
        return value.attr == "path" and isinstance(value.value, ast.Name) and value.value.id == "os"
    return False


class OsPathJoinAbsoluteLiteral(Check):
    code = "CH066"
    name = "os-path-join-absolute-literal"
    description = "os.path.join(...) is given a string literal starting with '/' partway through, discarding everything before it."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not _is_os_path_join(node) or len(node.args) < 2:
                continue
            for arg in node.args[1:]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith("/"):
                    findings.append(
                        Finding(
                            path=path,
                            line=arg.lineno,
                            col=arg.col_offset,
                            code=self.code,
                            message=(
                                f"{arg.value!r} starts with '/', so `os.path.join` restarts "
                                f"from it here, discarding every component before it - "
                                f"`os.path.join('/a', '/b')` is `/b`, not `/a/b`."
                            ),
                        )
                    )
        return findings
