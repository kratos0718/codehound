"""CH014 - Manual ``lock.acquire()`` / ``.release()`` with no ``try/finally``.

``lock.acquire()`` followed later by ``lock.release()`` as two independent
statements has a real gap: if anything between them raises, ``release()``
never runs and the lock stays held forever - every other coroutine/thread
that waits on it deadlocks. ``with lock:`` (or ``async with lock:``) exists
specifically to make this impossible; a bare, hand-rolled
acquire/release pair gives that safety up, usually without the author
intending to.

Only flags a lock whose ``.release()`` call exists **somewhere in the
function but never inside a `finally:` block** - a lock released inside
`finally:` is properly guarded regardless of exactly how the acquire is
written, so that's the one shape this treats as safe. This is
intentionally the least precise check here: it can't verify the acquire
and the guarded release are actually paired sequentially, only that both
calls exist and the release path includes an unguarded one - true to the
tool's "a finding is a lead" framing more than most of the others.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function, inside_with_statement


def _lock_receiver_name(call: ast.expr, attr: str) -> str | None:
    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == attr:
        if isinstance(call.func.value, ast.Name):
            return call.func.value.id
    return None


def _call_from_maybe_await(node: ast.AST) -> ast.expr | None:
    if isinstance(node, ast.Call):
        return node
    if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
        return node.value
    return None


class UnprotectedLockAcquire(Check):
    code = "CH014"
    name = "unprotected-lock-acquire"
    description = "lock.acquire() paired with an unguarded .release(); an exception between them deadlocks it."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr):
                continue
            call = _call_from_maybe_await(node.value)
            name = _lock_receiver_name(call, "acquire") if call is not None else None
            if name is None:
                continue
            if inside_with_statement(node, parents):
                continue

            fn = enclosing_function(node, parents)
            if fn is None:
                continue

            has_release = False
            has_guarded_release = False
            for n in ast.walk(fn):
                stmt = n.value if isinstance(n, ast.Expr) else n
                rel_call = _call_from_maybe_await(stmt) if isinstance(n, ast.Expr) else None
                if rel_call is not None and _lock_receiver_name(rel_call, "release") == name:
                    has_release = True
                    if self._inside_finally(n, parents) or self._inside_reraising_catchall(n, parents):
                        has_guarded_release = True

            if not has_release or has_guarded_release:
                continue

            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{name}.acquire()` has a matching `.release()` elsewhere in `{fn.name}`, "
                        f"but not inside a `finally:` block - an exception between acquire and "
                        f"release leaves `{name}` held forever. Use `with {name}:` "
                        f"(or `async with {name}:`) instead."
                    ),
                )
            )
        return findings

    @staticmethod
    def _inside_reraising_catchall(node: ast.AST, parents: dict) -> bool:
        """Release inside `except BaseException:`/bare `except:` that re-raises.

        Covers every failure path the way `finally:` would, and is the only
        correct spelling when the success path deliberately returns with the
        lock still held for a later, separate release (urllib3's HTTP/2
        probe cache: `acquire_and_get` hands the lock to its caller,
        `set_and_release` releases it).
        """
        cur = node
        while cur is not None:
            p = parents.get(id(cur))
            if p is None or isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            if isinstance(p, ast.ExceptHandler):
                t = p.type
                catches_all = t is None or (
                    (isinstance(t, ast.Name) and t.id == "BaseException")
                    or (isinstance(t, ast.Attribute) and t.attr == "BaseException")
                )
                reraises = any(isinstance(s, ast.Raise) for s in ast.walk(p))
                return catches_all and reraises
            cur = p
        return False

    @staticmethod
    def _inside_finally(node: ast.AST, parents: dict) -> bool:
        cur = node
        while cur is not None:
            p = parents.get(id(cur))
            if p is None:
                return False
            if isinstance(p, ast.Try) and cur in p.finalbody:
                return True
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return False
            cur = p
