"""CH020 - Bare ``except:`` (or unused ``except BaseException:``) catches everything.

A bare `except:` (or the explicit `except BaseException:`) doesn't just
catch the exception you meant to handle - it catches `KeyboardInterrupt`
and `SystemExit` too, meaning Ctrl-C stops working and `sys.exit()` gets
silently absorbed instead of actually exiting.

Not flagged when the handler either **uses** the bound exception (a real,
deliberate pattern found while building this: agno's background-thread
runner, `except BaseException as e: thread_error.append(e)`, surfacing
the exception to the consumer via a queue afterward - legitimate because
it's a worker thread reporting failures back, not discarding them) or
**re-raises anything** (another real pattern found the same way: agno's
`except BaseException: <reset internal state>; raise` - properly
propagates the original error to the caller after cleanup, so nothing is
actually swallowed). A bare `except:` with neither has no way to inspect
or propagate the exception at all, so it's flagged unconditionally.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _name_is_referenced(scope: ast.AST, name: str) -> bool:
    for node in ast.walk(scope):
        if isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Load):
            return True
    return False


def _has_raise_in_own_scope(handler: ast.ExceptHandler) -> bool:
    """Any `raise` in the handler's own reachable body - not counting a
    nested try/except's own handler, which is a different scope."""
    found = False

    def walk(node: ast.AST) -> None:
        nonlocal found
        if found:
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Raise):
                found = True
                return
            if isinstance(child, ast.ExceptHandler):
                continue
            walk(child)

    walk(handler)
    return found


class BareExcept(Check):
    code = "CH020"
    name = "bare-except"
    description = "Bare `except:` (or unused `except BaseException:`) also catches KeyboardInterrupt/SystemExit."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            is_bare = node.type is None
            is_base_exception = isinstance(node.type, ast.Name) and node.type.id == "BaseException"
            if not (is_bare or is_base_exception):
                continue
            if _has_raise_in_own_scope(node):
                continue
            if is_base_exception and node.name is not None:
                if any(_name_is_referenced(stmt, node.name) for stmt in node.body):
                    continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "bare `except:`" if is_bare else "`except BaseException:`"
                    )
                    + " also catches KeyboardInterrupt/SystemExit, and the exception isn't "
                    "used anywhere in the handler; catch the specific exception(s) this "
                    "handler is actually meant for.",
                )
            )
        return findings
