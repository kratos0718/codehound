"""CH036 - assigning directly to ``os.environ`` doesn't sync the real environment.

`os.environ` isn't a plain dict - it's a special mapping (`os._Environ`)
that calls `os.putenv`/`os.unsetenv` under the hood so the process's
*actual* environment (the C-level `environ`, the thing child processes
inherit) stays in sync with what Python sees. `os.environ = {...}`
doesn't call any of that - it just rebinds the module attribute to a
plain dict, leaving the real environment untouched. Verified directly:

    os.environ['TOKEN'] = 'secret'
    os.environ = {}
    subprocess.run([...])  # child process still sees TOKEN='secret'
    os.getenv('TOKEN')     # None - Python's own view says it's gone

Python's own view and the operating system's view now disagree, and
whichever one a test or a child process happens to read from decides
whether the "clear" actually took effect. This is flake8-bugbear's
B003, and it's exactly the kind of gotcha that looks like the obviously
correct way to reset environment state - `os.environ = old_snapshot`
inside a test's cleanup/`finally:` block is the single most common
place this shows up, precisely because it looks like a restore and
silently isn't one.

Only flags a direct assignment to the `os.environ` attribute -
`os.environ.clear()`, `os.environ.update(...)`, `os.environ.pop(...)`,
and `del os.environ[...]` all go through the real mapping and are all
correct, unflagged uses.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_os_environ_attribute(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "environ" and isinstance(node.value, ast.Name) and node.value.id == "os"


class EnvironReassignment(Check):
    code = "CH036"
    name = "environ-reassignment"
    description = "os.environ = ... rebinds the name but doesn't sync the real process environment; use .clear()/.update() instead."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if not _is_os_environ_attribute(target):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            "assigning directly to `os.environ` rebinds the name but doesn't "
                            "call putenv/unsetenv - the real process environment (what child "
                            "processes and `os.getenv` from C libraries see) stays unchanged. "
                            "Use `os.environ.clear()` and/or `.update(...)` instead."
                        ),
                    )
                )
                break
        return findings
