"""CH023 - a specific stdlib function/method that was removed, while its module lives on.

Unlike CH021 (a whole module gone), these are cases where the *module*
still imports fine but one particular name on it doesn't exist anymore:
`time.clock()` (removed 3.8, use `time.perf_counter()`/`.process_time()`),
`platform.linux_distribution()`/`.dist()` (removed 3.8, use the `distro`
package), `cgi.escape()` (removed 3.8 - years before the whole `cgi`
module went in 3.13, use `html.escape()`), and `base64.encodestring()`/
`.decodestring()` (removed 3.9, use `.encodebytes()`/`.decodebytes()`).
`AttributeError` on the call, same failure mode as the rest of this
family, just scoped to a single name instead of a whole import.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

# (module, attribute) -> (version removed, replacement)
_REMOVED: dict[tuple[str, str], tuple[str, str]] = {
    ("time", "clock"): ("3.8", "time.perf_counter() or time.process_time()"),
    ("platform", "linux_distribution"): ("3.8", "the `distro` package"),
    ("platform", "dist"): ("3.8", "the `distro` package"),
    ("cgi", "escape"): ("3.8", "html.escape()"),
    ("base64", "encodestring"): ("3.9", "base64.encodebytes()"),
    ("base64", "decodestring"): ("3.9", "base64.decodebytes()"),
}


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.asname or alias.name.split(".")[0])
    return modules


class RemovedStdlibAttribute(Check):
    code = "CH023"
    name = "removed-stdlib-attribute"
    description = "A specific stdlib function/method removed in a later Python version (time.clock, cgi.escape, etc)."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        imported = _imported_modules(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name):
                continue
            key = (node.value.id, node.attr)
            entry = _REMOVED.get(key)
            if entry is None:
                continue
            # Only trust `time.clock` etc when `import time` (or an alias of
            # it) was actually seen - `node.value.id` alone can't tell the
            # real module apart from an unrelated local of the same name.
            if node.value.id not in imported:
                continue
            version, replacement = entry
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{node.value.id}.{node.attr}` - removed in Python {version}; use "
                        f"{replacement} instead."
                    ),
                )
            )
        return findings
