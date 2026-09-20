"""CH086 - ``copy.deepcopy(self)`` inside a class whose own body
constructs a ``threading.Lock`` (or similar primitive) as an instance
attribute.

Verified directly:

    class HasLock:
        def __init__(self):
            self.lock = threading.Lock()
    copy.deepcopy(HasLock())
    # TypeError: cannot pickle '_thread.lock' object

`deepcopy` falls back to pickling protocol for objects it doesn't have a
special case for, and a lock (like a socket, a file handle, or a
`Condition`/`Semaphore`/`Event`) can't be pickled - there is no
general-purpose way to duplicate an OS-level synchronization primitive.
Any instance of a class holding one of these as an attribute raises the
moment something tries to deep-copy it, including the object copying
itself.

Only fires when the same class both constructs one of these primitives
as a `self.attr = ...` assignment somewhere in its own body, and calls
`copy.deepcopy(self)` somewhere in one of its own methods - a
single-class, self-contained check that doesn't try to trace whether some
other class instantiates and deep-copies this one from outside.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_LOCK_LIKE = {"Lock", "RLock", "Condition", "Semaphore", "BoundedSemaphore", "Event", "Barrier"}


def _is_lock_construction(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id in _LOCK_LIKE
    if isinstance(func, ast.Attribute):
        return func.attr in _LOCK_LIKE
    return False


def _lock_attr_names(cls: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign) and _is_lock_construction(node.value):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                    if target.value.id == "self":
                        names.add(target.attr)
    return names


def _is_deepcopy_self(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call) or len(node.args) != 1:
        return False
    func = node.func
    is_deepcopy = (isinstance(func, ast.Name) and func.id == "deepcopy") or (
        isinstance(func, ast.Attribute) and func.attr == "deepcopy"
    )
    return is_deepcopy and isinstance(node.args[0], ast.Name) and node.args[0].id == "self"


class DeepcopySelfWithLock(Check):
    code = "CH086"
    name = "deepcopy-self-with-lock"
    description = "copy.deepcopy(self) in a class that holds a threading.Lock/Condition/Event attribute always raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            lock_attrs = _lock_attr_names(cls)
            if not lock_attrs:
                continue
            for node in ast.walk(cls):
                if not _is_deepcopy_self(node):
                    continue
                attr_list = ", ".join(f"self.{a}" for a in sorted(lock_attrs))
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"copy.deepcopy(self) here always raises TypeError - "
                            f"`{cls.name}` constructs {attr_list} as an instance attribute, "
                            f"and locks/conditions/events can't be pickled or deep-copied."
                        ),
                    )
                )
        return findings
