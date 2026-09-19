"""CH050 - a dict comprehension's key never depends on its own loop variable.

`{key_expr: value_expr for x in items}` writes one entry per iteration
of `items`, but only if `key_expr` actually changes from one iteration
to the next - if `key_expr` doesn't reference `x` (or whatever the
comprehension's own loop variables are) at all, every iteration writes
to the *same* key, and each write silently overwrites the last.
Verified directly:

    items = [{"value": 1}, {"value": 2}, {"value": 3}]
    {"result": item["value"] for item in items}
    # {'result': 3} - only the last item survives; the first two
    # were computed and immediately discarded

This is flake8-bugbear's B035. The usual cause is a typo or a
copy-paste: the key expression references the wrong variable (an outer
one instead of the comprehension's own), so it reads as "one entry per
item" while actually producing at most one entry, full stop.

Flags a `DictComp` whose key expression contains no reference to any
name that actually varies per iteration - the `for`/tuple-unpacking
targets, *or* a walrus target bound anywhere in a generator's `if`
clauses. That second part isn't optional: the first corpus scan came
back with hits that were overwhelmingly one specific, common, entirely
correct idiom -

    {doc_hash: doc_id for doc_id, doc in items.items() if (doc_hash := doc.get("doc_hash"))}

- filtering *and* deriving the key in the same walrus, right there in
the `if` clause. `doc_hash` never appears in the `for` target, but it's
still bound fresh on every iteration - real hits in llama_index, vllm,
agno, pydantic-ai, and litellm all shared this exact shape. Also
deliberately backs off when the key itself contains a function call -
a nondeterministic one (`uuid.uuid4()`) can vary per iteration without
touching any loop variable at all, and this project would rather miss
that than guess wrong.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _target_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for elt in target.elts:
            names |= _target_names(elt)
        return names
    return set()


def _walrus_targets(node: ast.expr) -> set[str]:
    return {n.target.id for n in ast.walk(node) if isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name)}


def _has_call(node: ast.expr) -> bool:
    return any(isinstance(n, ast.Call) for n in ast.walk(node))


class StaticDictComprehensionKey(Check):
    code = "CH050"
    name = "static-dict-comprehension-key"
    description = "A dict comprehension's key doesn't reference its own loop variable - every iteration overwrites the same entry."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.DictComp):
                continue
            loop_vars: set[str] = set()
            for gen in node.generators:
                loop_vars |= _target_names(gen.target)
                loop_vars |= _walrus_targets(gen.iter)
                for if_clause in gen.ifs:
                    loop_vars |= _walrus_targets(if_clause)
            if not loop_vars:
                continue
            if _has_call(node.key) or _walrus_targets(node.key):
                continue
            key_names = {n.id for n in ast.walk(node.key) if isinstance(n, ast.Name)}
            if key_names & loop_vars:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.key.lineno,
                    col=node.key.col_offset,
                    code=self.code,
                    message=(
                        "this key never references the comprehension's own loop variable, so "
                        "every iteration writes to the same key - only the last item's value "
                        "survives, and every earlier one is silently discarded."
                    ),
                )
            )
        return findings
