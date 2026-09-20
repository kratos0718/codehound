"""CH094 - a call passes the same keyword both directly and through a
``**`` dict literal unpack.

Verified directly:

    def f(**kwargs): return kwargs
    f(a=1, **{'a': 2})
    # TypeError: f() got multiple values for keyword argument 'a'

Python resolves every keyword argument to a single parameter slot before
the call happens - an explicit `a=1` and a `**{'a': 2}` unpack both
target the same slot, and having both present is never valid, regardless
of which one the author meant to keep. This raises before the function
body ever runs.

Only fires when the `**`-unpacked argument is a dict literal with a
string-literal key equal to another keyword argument's name in the same
call - both sides statically known, not a runtime dict whose keys this
check can't see.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


class DuplicateKwargViaDictUnpack(Check):
    code = "CH094"
    name = "duplicate-kwarg-via-dict-unpack"
    description = "A call passes the same keyword both directly and through a **dict-literal unpack - raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            direct_names = {kw.arg for kw in node.keywords if kw.arg is not None}
            if not direct_names:
                continue
            for kw in node.keywords:
                if kw.arg is not None or not isinstance(kw.value, ast.Dict):
                    continue
                for key in kw.value.keys:
                    if (
                        isinstance(key, ast.Constant)
                        and isinstance(key.value, str)
                        and key.value in direct_names
                    ):
                        findings.append(
                            Finding(
                                path=path,
                                line=node.lineno,
                                col=node.col_offset,
                                code=self.code,
                                message=(
                                    f"this call passes `{key.value}` both as an explicit keyword "
                                    f"and inside the **-unpacked dict literal - both target the "
                                    f"same parameter, raising TypeError: got multiple values for "
                                    f"keyword argument '{key.value}'."
                                ),
                            )
                        )
        return findings
