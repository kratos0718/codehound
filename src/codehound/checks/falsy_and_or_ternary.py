"""CH060 - the pre-``if``/``else`` ``cond and a or b`` idiom breaks when
``a`` is falsy.

Verified directly: ``is_admin and 0 or 'default'`` evaluates to
``'default'`` even when ``is_admin`` is ``True``, because ``0`` is falsy,
so Python's ``or`` moves on to evaluate its right side regardless of
``is_admin``. This predates the real conditional expression
(``a if cond else b``, added in Python 2.5) and is a known-broken
substitute for it - it only silently gives the right answer when the
middle value happens to always be truthy, and only fires here when that
middle value is *staticaly* a falsy literal (``0``, ``0.0``, ``""``,
``False``, ``None``, ``[]``, ``{}``, ``()``), so this is never a false
positive: a real conditional expression exists precisely because this
pattern cannot be trusted with a value that might be falsy.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_falsy_literal(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return not node.value
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):
        return len(node.elts if isinstance(node, (ast.List, ast.Set)) else node.keys) == 0
    if isinstance(node, ast.Tuple):
        return len(node.elts) == 0
    return False


class FalsyAndOrTernary(Check):
    code = "CH060"
    name = "falsy-and-or-ternary"
    description = "`(cond and a) or b` silently picks `b` when `a` is a falsy literal, even if `cond` is true."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) >= 2):
                continue
            left = node.values[0]
            if not (isinstance(left, ast.BoolOp) and isinstance(left.op, ast.And) and len(left.values) >= 2):
                continue
            middle = left.values[-1]
            if not _is_falsy_literal(middle):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"The middle value here is always falsy, so `or` moves past it "
                        f"unconditionally - this always evaluates to the right-hand side, even "
                        f"when the left-hand condition is true. Use `a if cond else b` instead."
                    ),
                )
            )
        return findings
