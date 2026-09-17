"""CH021 - importing a stdlib module that no longer exists.

``distutils`` was deprecated in 3.10 and removed outright in 3.12 (PEP
632) - still one of the most common "why won't this install on the new
Python" reports, since it was the default build backend for `setup.py`
for two decades. `asynchat`/`asyncore`/`imp` were removed the same
release. Python 3.13 then removed the 19 modules PEP 594 called the
standard library's "dead batteries" - old data-format, multimedia, and
platform-specific modules with long-unmaintained implementations and
better replacements on PyPI (`aifc`, `audioop`, `cgi`, `cgitb`, `chunk`,
`crypt`, `imghdr`, `mailcap`, `msilib`, `nis`, `nntplib`, `ossaudiodev`,
`pipes`, `sndhdr`, `spwd`, `sunau`, `telnetlib`, `uu`, `xdrlib`).

Same failure mode as CH017/CH019: `ImportError` the moment the module is
loaded on the Python version it was removed in, not a subtle runtime
bug - but real, and common in anything with an older dependency tree or
a `setup.py` that hasn't been touched since distutils was normal.

Not flagged when the import sits in a `try:` body whose `except` catches
`ImportError` (or anything broader) - a real, deliberate pattern found in
agno: `try: import imghdr except ImportError: import filetype` explicitly
anticipates and falls back from exactly this removal, so it isn't a bug
waiting to happen, it's already handled.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_IMPORT_ERROR_NAMES = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _handles_import_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    candidates = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(c, ast.Name) and c.id in _IMPORT_ERROR_NAMES for c in candidates)


def _is_guarded_by_import_error_handler(node: ast.AST, parents: dict) -> bool:
    """True if `node` sits in the `try:` body of a Try with a matching
    handler, at any enclosing level up to the function/class/module
    boundary."""
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if p is None:
            return False
        if isinstance(p, ast.Try) and cur in p.body and any(_handles_import_error(h) for h in p.handlers):
            return True
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            return False
        cur = p
    return False

_REMOVED_IN: dict[str, str] = {
    "distutils": "3.12",
    "asynchat": "3.12",
    "asyncore": "3.12",
    "imp": "3.12",
    "aifc": "3.13",
    "audioop": "3.13",
    "cgi": "3.13",
    "cgitb": "3.13",
    "chunk": "3.13",
    "crypt": "3.13",
    "imghdr": "3.13",
    "mailcap": "3.13",
    "msilib": "3.13",
    "nis": "3.13",
    "nntplib": "3.13",
    "ossaudiodev": "3.13",
    "pipes": "3.13",
    "sndhdr": "3.13",
    "spwd": "3.13",
    "sunau": "3.13",
    "telnetlib": "3.13",
    "uu": "3.13",
    "xdrlib": "3.13",
}


class RemovedStdlibModule(Check):
    code = "CH021"
    name = "removed-stdlib-module"
    description = "Importing a stdlib module removed in a later Python version (distutils, PEP 594 modules, etc)."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if _is_guarded_by_import_error_handler(node, parents):
                    continue
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    version = _REMOVED_IN.get(top_level)
                    if version is not None:
                        findings.append(
                            Finding(
                                path=path,
                                line=node.lineno,
                                col=node.col_offset,
                                code=self.code,
                                message=(
                                    f"`import {alias.name}` - the `{top_level}` module was removed "
                                    f"in Python {version}; there is no drop-in stdlib replacement, "
                                    f"see its migration notes."
                                ),
                            )
                        )
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.level == 0
                and not _is_guarded_by_import_error_handler(node, parents)
            ):
                # `node.level` is the number of leading dots (0 = absolute). A
                # relative `from .chunk import x` has `node.module == "chunk"`
                # too - indistinguishable from the real stdlib module by name
                # alone. Real false positive found in vllm's own local
                # `fla/ops/chunk.py` sibling module, imported via `from .chunk
                # import chunk_gated_delta_rule`.
                top_level = node.module.split(".")[0]
                version = _REMOVED_IN.get(top_level)
                if version is not None:
                    names = ", ".join(alias.name for alias in node.names)
                    findings.append(
                        Finding(
                            path=path,
                            line=node.lineno,
                            col=node.col_offset,
                            code=self.code,
                            message=(
                                f"`from {node.module} import {names}` - the `{top_level}` module "
                                f"was removed in Python {version}; there is no drop-in stdlib "
                                f"replacement, see its migration notes."
                            ),
                        )
                    )
        return findings
