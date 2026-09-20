"""CH051 - mutating a dict/list/set while iterating directly over it by name.

``for k in d: del d[k]`` raises ``RuntimeError: dictionary changed size
during iteration`` the moment any key is added or removed mid-loop - verified
directly, it fires on the very first mutation, not just "sometimes." The same
shape on a ``list`` doesn't raise at all: removing an element shifts every
later index back by one, so the iterator - which just advances a plain
integer index - silently skips whatever slid into the position it already
passed. Both are the same mistake wearing different consequences: mutating
the exact object a loop is walking, instead of building a new one or
iterating over a snapshot (``for k in list(d):``).

Only flags a mutation whose receiver is the *same name* the ``for`` loop's
``iter`` expression is (or is a direct call on, e.g. ``d.keys()``/``d.items()``)
- mutating a different collection inside the loop is completely ordinary and
not flagged. Also excludes the single most common, completely safe shape
found by the first corpus scan: ``for key, value in d.items(): d[key] =
something`` - verified directly that re-assigning a key the loop is
*currently* holding never changes the dict's size, so it can never trigger
the ``RuntimeError`` this check exists to catch, unlike inserting a new key
or deleting one. Also excludes a mutation immediately followed by an
unconditional ``break`` in the same block - verified directly that Python's
dict iterator only raises on its *next* ``__next__()`` call after a size
change, so a loop that mutates and then leaves via `break` right there
never asks the iterator to advance again and never raises, a real pattern
found in transformers' own state-dict-renaming load hook.

``append``/``extend`` are deliberately not in the mutating-methods list at
all, even though they mutate the receiver: verified directly that appending
to the *end* of a list while iterating it with a plain `for` loop is safe
and behaves exactly as intended - the loop keeps advancing and does see the
newly-appended items, a well-known, deliberate growing-worklist pattern
(found for real in langgraph's own subgraph-search loop). This is different
from a set's `.add()`, which still raises `RuntimeError` immediately -
verified directly - since a set has no "end" to append at without checking
size, and different from `.insert()`, `.remove()`/`.pop()` and friends,
which change or depend on *existing* positions rather than only adding past
every position the loop has already reached.

Also recognizes one more shape of the same-key update, found for real in
pydantic's own JSON-schema remapper: ``for key, value in schema.items(): if
key == '$ref': schema['$ref'] = ...`` reassigns a key that's provably the
loop's current one, just spelled as the literal an enclosing ``if``/``elif``
already tested it against, rather than as the bound name directly.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_MUTATING_METHODS = {
    "insert",
    "remove",
    "pop",
    "clear",
    "update",
    "add",
    "discard",
    "popitem",
    "setdefault",
}


def _iterated_name(iter_expr: ast.expr) -> str | None:
    if isinstance(iter_expr, ast.Name):
        return iter_expr.id
    if (
        isinstance(iter_expr, ast.Call)
        and isinstance(iter_expr.func, ast.Attribute)
        and iter_expr.func.attr in ("keys", "values", "items")
        and isinstance(iter_expr.func.value, ast.Name)
    ):
        return iter_expr.func.value.id
    return None


def _is_receiver(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _bound_key_name(target: ast.expr, iter_expr: ast.expr) -> str | None:
    """The name a `for` loop binds to the *key* it's currently on, if any -
    `for k in d`/`for k in d.keys()` binds it directly; `for k, v in
    d.items()` binds it as the first element of the tuple target."""
    if isinstance(iter_expr, ast.Call) and isinstance(iter_expr.func, ast.Attribute):
        if iter_expr.func.attr == "items":
            if isinstance(target, ast.Tuple) and len(target.elts) == 2 and isinstance(target.elts[0], ast.Name):
                return target.elts[0].id
            return None
        if iter_expr.func.attr != "keys":
            return None
    if isinstance(target, ast.Name):
        return target.id
    return None


def _walk_own_expressions(stmt: ast.stmt):
    """Yield every node in `stmt`'s own fields, without descending into a
    nested compound statement's own body/orelse/handlers/finalbody - `ast.walk`
    has no way to stop at that boundary on its own, and those belong to a
    different block, handled by the caller's own recursion instead."""
    for field, value in ast.iter_fields(stmt):
        if field in ("body", "orelse", "handlers", "finalbody"):
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, ast.AST):
                yield from ast.walk(item)


def _equal_to_bound_key_literal(test: ast.expr, bound_key: str) -> str | None:
    """If `test` is (or `and`s together) `bound_key == 'literal'` (in either
    operand order), return that literal string."""
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        for value in test.values:
            found = _equal_to_bound_key_literal(value, bound_key)
            if found is not None:
                return found
        return None
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
        return None
    left, right = test.left, test.comparators[0]
    if isinstance(left, ast.Name) and left.id == bound_key and isinstance(right, ast.Constant):
        return right.value
    if isinstance(right, ast.Name) and right.id == bound_key and isinstance(left, ast.Constant):
        return left.value
    return None


def _mutation_in_stmt(
    stmt: ast.stmt, name: str, bound_key: str | None, known_safe_keys: frozenset[str]
) -> ast.AST | None:
    """Does `stmt` itself (anywhere in its own expressions, not in a nested
    compound statement's body) mutate `name`?"""
    if isinstance(stmt, ast.Delete):
        for tgt in stmt.targets:
            if isinstance(tgt, ast.Subscript) and _is_receiver(tgt.value, name):
                return stmt
    for node in _walk_own_expressions(stmt):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and _is_receiver(node.value, name):
            key_expr = node.slice
            if bound_key is not None and isinstance(key_expr, ast.Name) and key_expr.id == bound_key:
                continue
            if (
                isinstance(key_expr, ast.Constant)
                and isinstance(key_expr.value, str)
                and key_expr.value in known_safe_keys
            ):
                continue
            return node
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _MUTATING_METHODS
            and _is_receiver(node.func.value, name)
        ):
            return node
    return None


def _nested_blocks(stmt: ast.stmt) -> list[list[ast.stmt]]:
    """Sub-blocks whose statements still run as part of the *same* loop
    iteration - deliberately excludes For/AsyncFor/While bodies, which are a
    different loop's own scope (its own `break` doesn't exit the outer one).
    `If` is handled separately by `_blocks_with_safe_keys`, which needs its
    body/orelse paired with different safe-key sets - not reachable here."""
    if isinstance(stmt, ast.Try):
        return [stmt.body, *(h.body for h in stmt.handlers), stmt.orelse, stmt.finalbody]
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        return [stmt.body]
    return []


def _blocks_with_safe_keys(
    stmt: ast.stmt, bound_key: str | None, known_safe_keys: frozenset[str]
) -> list[tuple[list[ast.stmt], frozenset[str]]]:
    """Each sub-block that still runs as part of the same loop iteration,
    paired with the safe-key set that applies inside it - `if bound_key ==
    'literal':`'s own body gets that literal added, its `orelse` doesn't."""
    if isinstance(stmt, ast.If):
        body_keys = known_safe_keys
        if bound_key is not None:
            literal = _equal_to_bound_key_literal(stmt.test, bound_key)
            if literal is not None:
                body_keys = known_safe_keys | {literal}
        return [(stmt.body, body_keys), (stmt.orelse, known_safe_keys)]
    return [(block, known_safe_keys) for block in _nested_blocks(stmt)]


def _find_mutation(
    body: list[ast.stmt], name: str, bound_key: str | None, known_safe_keys: frozenset[str] = frozenset()
) -> ast.AST | None:
    for i, stmt in enumerate(body):
        mutation = _mutation_in_stmt(stmt, name, bound_key, known_safe_keys)
        if mutation is not None:
            if i + 1 < len(body) and isinstance(body[i + 1], ast.Break):
                continue  # never asks the iterator to advance again
            return mutation
        for block, block_safe_keys in _blocks_with_safe_keys(stmt, bound_key, known_safe_keys):
            found = _find_mutation(block, name, bound_key, block_safe_keys)
            if found is not None:
                return found
    return None


class MutationDuringIteration(Check):
    code = "CH051"
    name = "mutation-during-iteration"
    description = "A dict/list/set is mutated inside a loop that is iterating directly over it."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.For, ast.AsyncFor)):
                continue
            name = _iterated_name(node.iter)
            if name is None:
                continue
            bound_key = _bound_key_name(node.target, node.iter)
            mutation = _find_mutation(node.body, name, bound_key)
            if mutation is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=mutation.lineno,
                    col=mutation.col_offset,
                    code=self.code,
                    message=(
                        f"`{name}` is mutated here while the enclosing loop iterates over it "
                        f"directly - for a dict/set this raises `RuntimeError: ... changed size "
                        f"during iteration`, for a list it silently skips elements instead. "
                        f"Iterate over a snapshot instead: `for x in list({name}):`."
                    ),
                )
            )
        return findings
