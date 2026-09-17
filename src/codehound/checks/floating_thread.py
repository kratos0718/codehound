"""CH009 - Non-daemon ``threading.Thread`` started without a matching ``join()``.

The thread analog of CH006's floating-task: a plain ``threading.Thread``
that gets ``.start()``ed but never joined keeps running independently of
whoever created it. Unlike a daemon thread (an explicit, intentional
"let this die with the process" choice), a *non*-daemon thread that's
never joined can outlive the function that spawned it, hold the
interpreter open past when the caller expects the program to exit, or
race with cleanup code that assumed the work was done because the
function that started it returned.

Two shapes:
- Chained: ``threading.Thread(target=f).start()`` - the thread object is
  never even captured, so joining it later is structurally impossible.
- Assigned: ``t = threading.Thread(target=f); t.start()`` - captured, but
  no matching ``t.join()`` (and not returned, not stored as an attribute
  of anything, not marked ``daemon=True``) before the enclosing function
  returns.

A real false positive found while building this: llama_index's chat
engines create the thread, then do ``chat_response.write_response_to_history_thread
= thread`` and return ``chat_response`` - the thread isn't lost, it's
handed off through a *different* object's attribute (not ``self``), and
gets joined later once the caller finishes consuming the stream
(``chat_engine/types.py``). The escape check below treats a thread
assigned as *any* object's attribute as a deliberate hand-off, not just
``self.<attr>``.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


def _is_thread_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "Thread"
    if isinstance(func, ast.Attribute):
        return func.attr == "Thread" and isinstance(func.value, ast.Name) and func.value.id == "threading"
    return False


def _has_daemon_true_kwarg(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "daemon" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
            return True
    return False


class FloatingThread(Check):
    code = "CH009"
    name = "floating-thread"
    description = "Non-daemon threading.Thread started without a matching join()."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []

        # Chained: threading.Thread(...).start() with no assignment at all.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not (isinstance(call.func, ast.Attribute) and call.func.attr == "start"):
                continue
            receiver = call.func.value
            if not _is_thread_call(receiver):
                continue
            if _has_daemon_true_kwarg(receiver):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "`threading.Thread(...).start()` - the thread is never captured, so it "
                        "can never be joined; either keep a reference and join() it, or pass "
                        "`daemon=True` if letting it outlive this scope is intentional."
                    ),
                )
            )

        # Assigned: t = threading.Thread(...); ... t.start() ... [no t.join()]
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not _is_thread_call(node.value):
                continue
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            call = node.value
            if _has_daemon_true_kwarg(call):
                continue

            fn = enclosing_function(node, parents)
            if fn is None:
                continue

            started = False
            joined = False
            escapes = False
            for n in ast.walk(fn):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(
                    n.func.value, ast.Name
                ) and n.func.value.id == name:
                    if n.func.attr == "start":
                        started = True
                    elif n.func.attr == "join":
                        joined = True
                elif isinstance(n, ast.Assign):
                    for tgt in n.targets:
                        if (
                            isinstance(tgt, ast.Attribute)
                            and tgt.attr != "daemon"
                            and isinstance(n.value, ast.Name)
                            and n.value.id == name
                        ):
                            # Stored as an attribute of *any* object (not just
                            # self) - e.g. a response object that hands the
                            # thread off to its own caller for later joining.
                            # Real pattern: llama_index's chat_engine classes
                            # stash the thread on the StreamingAgentChatResponse
                            # they return, which joins it once the stream is
                            # fully consumed (chat_engine/types.py).
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

            if not started or joined or escapes:
                continue

            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`{name} = threading.Thread(...)` in `{fn.name}` is started but never "
                        f"joined; it can outlive this function. Call `{name}.join()`, return it "
                        f"to the caller, or pass `daemon=True` if that's intentional."
                    ),
                )
            )
        return findings
