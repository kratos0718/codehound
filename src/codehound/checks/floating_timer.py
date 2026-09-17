"""CH028 - ``threading.Timer`` started without keeping a way to cancel it.

A `Timer` schedules its callback to run *later*, on its own thread, once
the interval elapses. Unlike a plain `Thread` doing work right now, the
risk with an un-captured or un-cancelled `Timer` isn't just "outlives the
function" - it's that nothing can stop the callback from firing after
the context it was meant to act on is already gone: a retry timer that
fires after the operation it would retry has already completed, a
debounce timer that resets state on an object that was already torn
down. `.cancel()` before that happens is the only way to prevent it; if
nothing ever keeps a reference capable of calling it, the callback is
guaranteed to run no matter what changes in the meantime.

Same two shapes as CH009's floating-thread:
- Chained: ``threading.Timer(30, cb).start()`` - never captured, so
  cancelling it later is structurally impossible.
- Assigned: ``t = threading.Timer(30, cb); t.start()`` - captured, but no
  matching ``t.cancel()`` before the enclosing function returns, and not
  handed off (returned, stored as any object's attribute), and not
  marked ``daemon=True`` (a deliberate "let this outlive the caller"
  choice, the same escape CH009 recognizes).

A bare ``Timer(...)`` is only trusted to mean `threading.Timer` if the
file actually imported it via `from threading import Timer` - the same
name-collision guard CH018/CH022 use. A real false positive found while
building this: agno defines its own unrelated stopwatch-style `Timer`
class (`from agno.utils.timer import Timer`, called as `Timer()` with no
arguments at all - `threading.Timer` requires `interval` and `function`
and would raise `TypeError` immediately if it were really that class),
and every one of its ~30 corpus hits was this same collision.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


def _imports_timer_from_threading(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "threading":
            if any(alias.name == "Timer" for alias in node.names):
                return True
    return False


def _is_timer_call(node: ast.expr, trust_bare_name: bool) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "Timer" and isinstance(func.value, ast.Name) and func.value.id == "threading"
    if isinstance(func, ast.Name):
        return trust_bare_name and func.id == "Timer"
    return False


def _has_daemon_true_kwarg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "daemon" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


class FloatingTimer(Check):
    code = "CH028"
    name = "floating-timer"
    description = "threading.Timer started without keeping a way to cancel() it."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        trust_bare_name = _imports_timer_from_threading(tree)

        # Chained: threading.Timer(...).start() with no assignment at all.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "start"):
                continue
            receiver = call.func.value
            if not _is_timer_call(receiver, trust_bare_name):
                continue
            if isinstance(receiver, ast.Call) and _has_daemon_true_kwarg(receiver):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "`threading.Timer(...).start()` - the timer is never captured, so it can "
                        "never be cancelled; keep a reference so it can be cancel()ed if the "
                        "context it would act on goes away before it fires."
                    ),
                )
            )

        # Assigned: t = threading.Timer(...); ... t.start() ... [no t.cancel()]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_timer_call(node.value, trust_bare_name):
                continue
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            if _has_daemon_true_kwarg(node.value):
                continue

            fn = enclosing_function(node, parents)
            if fn is None:
                continue

            started = False
            cancelled = False
            escapes = False
            for n in ast.walk(fn):
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == name
                ):
                    if n.func.attr == "start":
                        started = True
                    elif n.func.attr == "cancel":
                        cancelled = True
                elif isinstance(n, ast.Assign):
                    for tgt in n.targets:
                        if (
                            isinstance(tgt, ast.Attribute)
                            and tgt.attr != "daemon"
                            and isinstance(n.value, ast.Name)
                            and n.value.id == name
                        ):
                            # Handed off as any object's attribute - the
                            # receiver can cancel it later.
                            escapes = True
                        if (
                            isinstance(tgt, ast.Attribute)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == name
                            and tgt.attr == "daemon"
                            and isinstance(n.value, ast.Constant)
                            and n.value.value is True
                        ):
                            escapes = True  # daemon set post-construction
                elif isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == name:
                    escapes = True

            if not started or cancelled or escapes:
                continue

            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{name} = threading.Timer(...)` in `{fn.name}` is started but never "
                        f"cancelled or handed off; nothing can stop it from firing later. Call "
                        f"`{name}.cancel()` when it's no longer needed, return/store it so the "
                        f"caller can, or pass `daemon=True` if that's intentional."
                    ),
                )
            )
        return findings
