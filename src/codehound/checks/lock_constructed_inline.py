"""CH039 - a lock/semaphore constructed inline in the `with` that acquires it.

A lock only does anything if more than one caller can reach the *same*
object - mutual exclusion is exclusion against other holders of that
exact lock, not against the world in general. `with threading.Lock():`
constructs a brand-new, never-shared lock, acquires it, runs the block,
and releases it; nothing else in the process has any way to ever see
that object, so nothing ever contends for it. It isn't a crash - it's
a no-op that reads like synchronization and provides none. Verified
directly: five threads, each doing `with threading.Lock():` around an
0.01s sleep, finished in ~0.013s total, not the ~0.05s they'd take if
the lock were actually serializing them - the "critical section" ran
fully concurrently.

Not in flake8-bugbear, pylint, or Ruff as far as this project could
find - it's in the same family as CH009/CH012/CH028/CH031 (a floating
threading/multiprocessing primitive that does nothing useful), but
those are about a primitive that's *never cleaned up*; this one is
about a primitive that's *never shared*, a different way to
accidentally not synchronize.

Deliberately narrow: only the exact syntactic shape where the lock is
constructed directly in the `with`/`async with` itself
(`with threading.Lock():`) is flagged. `lock = threading.Lock()` on one
line and `with lock:` on the next is the same bug, but telling that
apart from `self.lock = threading.Lock()` (correct, shared, just not
in this exact function) needs tracing the name across statements and
scopes - out of scope for a single-pass AST check without introducing
that kind of guesswork.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_LOCK_CONSTRUCTORS: dict[tuple[str, str], str] = {
    ("threading", "Lock"): "threading.Lock()",
    ("threading", "RLock"): "threading.RLock()",
    ("multiprocessing", "Lock"): "multiprocessing.Lock()",
    ("multiprocessing", "RLock"): "multiprocessing.RLock()",
    ("asyncio", "Lock"): "asyncio.Lock()",
}


def _inline_lock_name(expr: ast.expr) -> str | None:
    if not isinstance(expr, ast.Call):
        return None
    func = expr.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        return _LOCK_CONSTRUCTORS.get((func.value.id, func.attr))
    return None


class LockConstructedInline(Check):
    code = "CH039"
    name = "lock-constructed-inline"
    description = "A lock/RLock constructed directly in the with statement that acquires it can never be shared, so it never synchronizes anything."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            for item in node.items:
                lock_name = _inline_lock_name(item.context_expr)
                if lock_name is None:
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=item.context_expr.lineno,
                        col=item.context_expr.col_offset,
                        code=self.code,
                        message=(
                            f"`{lock_name}` is constructed right here, so nothing else in the "
                            f"process can ever hold a reference to it - this lock can never be "
                            f"contended, which means it never actually synchronizes anything. "
                            f"Construct it once (e.g. in `__init__`) and reuse the same instance."
                        ),
                    )
                )
        return findings
