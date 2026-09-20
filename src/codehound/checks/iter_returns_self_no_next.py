"""CH100 - ``__iter__`` returns ``self``, but the class defines no
``__next__``.

Verified directly:

    class Foo:
        def __iter__(self):
            return self

    for x in Foo():
        print(x)
    # TypeError: iter() returned non-iterator of type 'Foo'

Returning `self` from `__iter__` is the standard way to make an object
directly iterable, but it's a contract: whatever `__iter__` returns has
to actually satisfy the iterator protocol, which means having a working
`__next__`. Returning `self` without ever defining `__next__` promises
an iterator the class doesn't deliver - `iter(x)` itself succeeds (it
just calls `__iter__`), and the failure only surfaces one step later, at
the first `next()` call.

Only fires when the class has no base classes at all (a pure `object`
subclass, so there's no possibility a base class supplies `__next__`)
and its own body defines `__iter__` returning `self` but no `__next__`.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _returns_self(method: ast.FunctionDef | ast.AsyncFunctionDef, self_name: str) -> ast.Return | None:
    for node in ast.walk(method):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id == self_name:
            return node
    return None


class IterReturnsSelfNoNext(Check):
    code = "CH100"
    name = "iter-returns-self-no-next"
    description = "__iter__ returns self, but the class defines no __next__ - iter() succeeds, next() raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef) or cls.bases:
                continue
            iter_method = next(
                (s for s in cls.body if isinstance(s, ast.FunctionDef) and s.name == "__iter__"), None
            )
            if iter_method is None or not iter_method.args.args:
                continue
            has_next = any(isinstance(s, ast.FunctionDef) and s.name == "__next__" for s in cls.body)
            if has_next:
                continue
            self_name = iter_method.args.args[0].arg
            hit = _returns_self(iter_method, self_name)
            if hit is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=hit.lineno,
                    col=hit.col_offset,
                    code=self.code,
                    message=(
                        f"`{cls.name}.__iter__` returns `{self_name}`, but `{cls.name}` defines "
                        f"no `__next__` - iter() on this object succeeds, but the first next() "
                        f"call raises TypeError: iter() returned non-iterator."
                    ),
                )
            )
        return findings
