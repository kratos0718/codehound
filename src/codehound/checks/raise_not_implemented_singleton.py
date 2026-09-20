"""CH097 - ``raise NotImplemented`` instead of ``raise NotImplementedError()``.

Verified directly:

    def f():
        raise NotImplemented
    f()
    # TypeError: exceptions must derive from BaseException

`NotImplemented` is a singleton value, the same category of object as
`True`/`False`/`None` - it's meant to be *returned* from a binary special
method (`__eq__`, `__add__`, ...) to tell Python "try the other operand's
version instead", never raised. `NotImplementedError` is the actual
exception class meant for a stub method. The two are one letter apart
and easy to autocomplete into the wrong one, and unlike most typos this
one isn't caught by any type checker - `NotImplemented`'s type really is
a valid-looking object, just not an exception.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class RaiseNotImplementedSingleton(Check):
    code = "CH097"
    name = "raise-not-implemented-singleton"
    description = "raise NotImplemented (the singleton, not NotImplementedError) always raises TypeError instead."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            if isinstance(node.exc, ast.Name) and node.exc.id == "NotImplemented":
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            "raise NotImplemented raises the singleton value, not an exception - "
                            "Python requires exceptions to derive from BaseException, so this "
                            "always raises TypeError instead. Use NotImplementedError() (with "
                            "parens, a real exception class) if the intent is 'not implemented yet'."
                        ),
                    )
                )
        return findings
