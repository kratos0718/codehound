"""CH025 - ``is``/``is not`` comparing against a str/bytes/int/float literal.

`is` checks object *identity*, not equality - `x is 5` only happens to
work because CPython caches small integers (-5 to 256) and sometimes
interns short string literals, neither of which is a language guarantee.
`x is 1000` can be `False` even when `x == 1000` is `True`, and whether a
given string literal gets interned depends on the compiler and the
string's exact contents. Code that "works" this way is one PyPy run, one
larger number, or one differently-compiled string away from silently
returning the wrong answer - this is pyflakes' own F632, included here
because a bug this easy to introduce by typo (`is` for `==`) and this
quiet when it happens to pass by accident earns a place in a tool whose
whole premise is "subtle correctness bugs," not just style.

`is None` / `is True` / `is False` / `is ...` are the actual idiomatic
uses of `is` and are never flagged.

A chained comparison (`a in b is not None`) has every operand and every
op in one `ast.Compare` node, but they aren't a free-for-all - each op
only applies to the two operands adjacent to it. `"usage" in response_obj
is not None` is `("usage" in response_obj) and (response_obj is not
None)`: the string literal is the left side of `in`, not of `is not`,
which is actually comparing `response_obj` against the *allowed*
singleton `None`. Real false positive found in litellm: checking "is
there a literal anywhere in the chain" and "is there an Is/IsNot op
anywhere in the chain" independently, without pairing each op with its
own adjacent operands, matched this for the wrong reason. Fixed by
walking the chain as adjacent (left, op, right) triples.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_ALLOWED_SINGLETONS = (None, True, False, Ellipsis)


def _is_flagged_literal(node: ast.expr) -> bool:
    if not isinstance(node, ast.Constant):
        return False
    value = node.value
    if any(value is s for s in _ALLOWED_SINGLETONS):
        return False
    return isinstance(value, (str, bytes, int, float, complex))


class IsLiteralComparison(Check):
    code = "CH025"
    name = "is-literal-comparison"
    description = "`is`/`is not` compares identity, not equality; use ==/!= for str/bytes/int/float literals."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            operands = [node.left, *node.comparators]
            for left, op, right in zip(operands, node.ops, operands[1:]):
                if not isinstance(op, (ast.Is, ast.IsNot)):
                    continue
                if not (_is_flagged_literal(left) or _is_flagged_literal(right)):
                    continue
                op_text = "is not" if isinstance(op, ast.IsNot) else "is"
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{op_text}` compares identity, not equality - comparing against a "
                            f"literal here relies on CPython implementation details (small-int "
                            f"caching, string interning) that aren't guaranteed; use "
                            f"`{'!=' if op_text == 'is not' else '=='}` instead."
                        ),
                    )
                )
        return findings
