"""CH053 - ``[mutable_literal] * n`` creates ``n`` references to the *same*
mutable object, not ``n`` independent copies, when the result is later
indexed and mutated cell-by-cell.

``grid = [[0] * cols] * rows`` is the classic 2D-list-initialization trap.
Verified directly: mutating ``grid[0][0]`` changes every row, because
list-repetition (``*``) never copies elements - it just repeats the same
object reference ``n`` times.

Only fires when the repeated list is assigned to a plain name, and that
name is *later* subscripted with a nested store (``name[i][j] = ...``) -
the shape that actually exercises the aliasing. The first corpus scan found
this construction is overwhelmingly used a different, harmless way in
AI/ML code: building a `[[shape_metadata]] * batch_size`-style literal that
feeds straight into a dict, a tensor constructor, or another function, and
is never indexed into a second time - the aliasing there is real but inert,
since nothing ever asks two of the "rows" to be independent. Narrowing to
provable later cell-mutation cut a 58-hit false-positive cluster in
transformers (the same broadcast-metadata idiom copy-pasted across dozens
of model image processors) down to zero, while still catching the
textbook mistake this check exists for.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_mutable_literal(node: ast.expr) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return True
    # `[0] * cols` (or `cols * [0]`) is itself a list - the classic
    # `[[0] * cols] * rows` 2D case nests exactly this shape one level in.
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return isinstance(node.left, ast.List) or isinstance(node.right, ast.List)
    return False


def _repeated_mutable_list(node: ast.expr) -> ast.List | None:
    """If `node` is `[mutable_literal] * n` or `n * [mutable_literal]`, return
    the outer list literal being repeated."""
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
        return None
    for side in (node.left, node.right):
        if isinstance(side, ast.List) and len(side.elts) == 1 and _is_mutable_literal(side.elts[0]):
            return side
    return None


def _is_nested_subscript_store(node: ast.AST, name: str) -> bool:
    """`name[i][j] = ...` - a Store subscript whose own value is itself a
    subscript of `name` (of any depth of indexing)."""
    if not (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store)):
        return False
    inner = node.value
    while isinstance(inner, ast.Subscript):
        inner = inner.value
    return isinstance(inner, ast.Name) and inner.id == name


class AliasedListMultiplication(Check):
    code = "CH053"
    name = "aliased-list-multiplication"
    description = "A [mutable_literal] * n result is later indexed and mutated cell-by-cell, exposing the aliasing."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
                continue
            body = func.body
            for i, stmt in enumerate(body):
                if not (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                ):
                    continue
                repeated = _repeated_mutable_list(stmt.value)
                if repeated is None:
                    continue
                name = stmt.targets[0].id
                mutated_later = any(
                    _is_nested_subscript_store(node, name) for later in body[i + 1 :] for node in ast.walk(later)
                )
                if not mutated_later:
                    continue
                element = repeated.elts[0]
                kind = "list" if isinstance(element, ast.BinOp) else type(element).__name__.lower()
                findings.append(
                    Finding(
                        path=path,
                        line=stmt.value.lineno,
                        col=stmt.value.col_offset,
                        code=self.code,
                        message=(
                            f"`{name}` is built by repeating a {kind} literal with `*`, which "
                            f"copies the *reference* n times, not the {kind} itself - every "
                            f"element still points at the same object, so the cell-by-cell "
                            f"mutation below is visible through all of them. Use a comprehension "
                            f"instead, e.g. `[... for _ in range(n)]`."
                        ),
                    )
                )
        return findings
