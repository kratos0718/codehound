"""CH012 - Non-daemon ``multiprocessing.Process`` started without a matching ``join()``.

The process analog of CH009's floating-thread, and arguably worse: a
never-joined child process can become a real zombie (consuming a PID/OS
process-table slot until its parent reaps it) rather than just an
in-process thread the GC eventually notices. Same two shapes, same escape
rules: a thread/process handed off via a return value or stashed as any
object's attribute is an intentional hand-off, not a leak (see CH009 for
the real llama_index false positive that shaped this rule).
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


def _is_process_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Process"
    if isinstance(func, ast.Attribute):
        return func.attr == "Process" and isinstance(func.value, ast.Name) and func.value.id == "multiprocessing"
    return False


def _has_daemon_true_kwarg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "daemon" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


class FloatingProcess(Check):
    code = "CH012"
    name = "floating-process"
    description = "Non-daemon multiprocessing.Process started without a matching join()."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "start"):
                continue
            receiver = call.func.value
            if not _is_process_call(receiver) or _has_daemon_true_kwarg(receiver):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "`multiprocessing.Process(...).start()` - the process is never "
                        "captured, so it can never be joined or reaped explicitly; either keep "
                        "a reference and join() it, or pass `daemon=True` if that's intentional."
                    ),
                )
            )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_process_call(node.value):
                continue
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            if _has_daemon_true_kwarg(node.value):
                continue

            fn = enclosing_function(node, parents)
            if fn is None:
                continue

            started = joined = escapes = False
            for n in ast.walk(fn):
                if (
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == name
                ):
                    if n.func.attr == "start":
                        started = True
                    elif n.func.attr in ("join", "close"):
                        joined = True
                elif isinstance(n, ast.Assign):
                    for tgt in n.targets:
                        if (
                            isinstance(tgt, ast.Attribute)
                            and tgt.attr != "daemon"
                            and isinstance(n.value, ast.Name)
                            and n.value.id == name
                        ):
                            escapes = True
                        if (
                            isinstance(tgt, ast.Attribute)
                            and isinstance(tgt.value, ast.Name)
                            and tgt.value.id == name
                            and tgt.attr == "daemon"
                            and isinstance(n.value, ast.Constant)
                            and n.value.value is True
                        ):
                            escapes = True
                elif isinstance(n, ast.Return) and isinstance(n.value, ast.Name) and n.value.id == name:
                    escapes = True

            if not started or joined or escapes:
                continue

            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{name} = multiprocessing.Process(...)` in `{fn.name}` is started but "
                        f"never joined; call `{name}.join()`, return it to the caller, or pass "
                        f"`daemon=True` if outliving this function is intentional."
                    ),
                )
            )
        return findings
