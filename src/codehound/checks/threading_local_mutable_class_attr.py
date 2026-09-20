"""CH070 - a ``threading.local`` subclass with a class-level mutable
attribute leaks that object across every thread.

Verified directly: ``class MyLocal(threading.local): items = []`` then
mutating ``local_instance.items`` from one thread and reading it from
another shows the *same* list, growing across threads - the second
thread's output includes the first thread's entry. `threading.local`
gives each thread its own separate namespace for attributes actually
*set* on an instance, but a class-level attribute is looked up on the
class itself, exactly like any other Python class attribute - completely
unaffected by which thread is asking. This is the same underlying
mistake as CH026's mutable class attribute, but on the one class whose
entire purpose is thread isolation, silently failing at exactly that job.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_threading_local_base(base: ast.expr) -> bool:
    if isinstance(base, ast.Name):
        return base.id == "local"
    return isinstance(base, ast.Attribute) and base.attr == "local"


def _is_mutable_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set")


class ThreadingLocalMutableClassAttr(Check):
    code = "CH070"
    name = "threading-local-mutable-class-attr"
    description = "A threading.local subclass's class-level mutable attribute is shared across every thread."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef) or not any(_is_threading_local_base(b) for b in cls.bases):
                continue
            for stmt in cls.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and _is_mutable_literal(stmt.value)
                ):
                    findings.append(
                        Finding(
                            path=path,
                            line=stmt.lineno,
                            col=stmt.col_offset,
                            code=self.code,
                            message=(
                                f"`{cls.name}.{stmt.targets[0].id}` is a class-level mutable "
                                f"default on a `threading.local` subclass - it's looked up on "
                                f"the class itself, the same for every thread, silently "
                                f"defeating the whole point of `threading.local`."
                            ),
                        )
                    )
        return findings
