"""CH029 - ``return``/``break``/``continue`` in a ``finally:`` block silently drops any pending exception.

If the `try:` body raises, and the matching `finally:` block runs a
`return`, or a `break`/`continue` that jumps to a loop outside the
`finally` block itself, the exception is discarded entirely - not
logged, not re-raised, nothing. Verified directly:

    def f():
        try:
            raise ValueError("boom")
        finally:
            return 5

`f()` returns `5`. The `ValueError` never happens as far as the caller
can tell. This is documented CPython behavior, not a bug in Python
itself, but it means an exception can vanish from a `finally:` block
that looks like ordinary cleanup code, with nothing in the syntax
calling out that it swallows errors - pylint's own `lost-exception`
(W0150) exists for exactly this.

A `break`/`continue` fully contained within a loop that itself lives
inside the `finally:` block is a different, local loop and does not
escape - only a `break`/`continue` whose target loop is *outside* the
`finally:` block (an ancestor of the whole `try` statement) swallows
the pending exception. Verified directly for both shapes.

Not flagged when the `try` has at least one `except` clause and none of
them ever re-raise: at that point every exception the `try` body could
produce has already been fully handled by the time control reaches
`finally`, so a `return`/`break`/`continue` there is just the
function's normal exit for the already-handled path, not a swallow.
Real pattern found in letta: `except Exception as e: result["error"] =
str(e)` (logged, recorded, deliberately not re-raised, the docstring
literally says "callback failures should not affect job completion")
followed by `finally: return result` - nothing is pending to discard.
A `try` with *no* `except` at all is unaffected by this guard, since
nothing there could have absorbed anything.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _has_escaping_return(stmts: list[ast.stmt]) -> ast.Return | None:
    def walk(node: ast.AST) -> ast.Return | None:
        if isinstance(node, ast.Return):
            return node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return None
        for child in ast.iter_child_nodes(node):
            found = walk(child)
            if found is not None:
                return found
        return None

    for stmt in stmts:
        found = walk(stmt)
        if found is not None:
            return found
    return None


def _owning_loop_is_outside_finally(node: ast.AST, try_node: ast.Try, parents: dict) -> bool:
    cur: ast.AST | None = node
    while cur is not None and cur is not try_node:
        if isinstance(cur, (ast.For, ast.AsyncFor, ast.While)):
            return False
        cur = parents.get(id(cur))
    return True


def _find_escaping_break_or_continue(
    stmts: list[ast.stmt], try_node: ast.Try, parents: dict
) -> ast.stmt | None:
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, (ast.Break, ast.Continue)) and _owning_loop_is_outside_finally(
                node, try_node, parents
            ):
                return node
    return None


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


def _fully_absorbs_exceptions(try_node: ast.Try) -> bool:
    if not try_node.handlers:
        return False
    return all(not _has_raise_in_own_scope(h) for h in try_node.handlers)


class FinallySwallowsException(Check):
    code = "CH029"
    name = "finally-swallows-exception"
    description = "return/break/continue in a finally: block silently discards any exception from the try:."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try) or not node.finalbody:
                continue
            if _fully_absorbs_exceptions(node):
                continue
            culprit: ast.stmt | None = _has_escaping_return(node.finalbody)
            kind = "return"
            if culprit is None:
                culprit = _find_escaping_break_or_continue(node.finalbody, node, parents)
                kind = "break" if isinstance(culprit, ast.Break) else "continue"
            if culprit is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=culprit.lineno,
                    col=culprit.col_offset,
                    code=self.code,
                    message=(
                        f"`{kind}` in this `finally:` block silently discards any exception "
                        f"raised in the `try:` body - the caller never sees it. Move the "
                        f"{kind} out of `finally:`, or re-raise explicitly if that's intended."
                    ),
                )
            )
        return findings
