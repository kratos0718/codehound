"""CH078 - ``self.x = ...`` inside ``__post_init__`` of a
``@dataclass(frozen=True)`` class.

Verified directly:

    @dataclass(frozen=True)
    class F:
        x: int
        def __post_init__(self):
            self.x = self.x * 2
    F(5)   # dataclasses.FrozenInstanceError: cannot assign to field 'x'

A frozen dataclass blocks *every* attribute assignment through
`__setattr__`, including ones made from inside its own `__post_init__` -
there's no special exemption for code the dataclass itself calls. The
documented workaround is `object.__setattr__(self, "x", value)`, which
bypasses the frozen class's own `__setattr__` entirely; that form is a
`Call`, not an `Assign`, so it's never flagged here.

Only fires on a direct `self.attr = ...` or `self.attr += ...` inside
`__post_init__`, in a class whose `@dataclass(...)` decorator has an
explicit `frozen=True` keyword.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_frozen_dataclass_decorator(dec: ast.expr) -> bool:
    if not isinstance(dec, ast.Call):
        return False
    func = dec.func
    is_dataclass = (isinstance(func, ast.Name) and func.id == "dataclass") or (
        isinstance(func, ast.Attribute) and func.attr == "dataclass"
    )
    if not is_dataclass:
        return False
    return any(
        kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in dec.keywords
    )


class FrozenDataclassPostInitMutation(Check):
    code = "CH078"
    name = "frozen-dataclass-post-init-mutation"
    description = "self.x = ... inside __post_init__ of a frozen dataclass raises FrozenInstanceError on every construction."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if not any(_is_frozen_dataclass_decorator(d) for d in cls.decorator_list):
                continue
            post_init = next(
                (
                    s
                    for s in cls.body
                    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == "__post_init__"
                ),
                None,
            )
            if post_init is None or not post_init.args.args:
                continue
            self_name = post_init.args.args[0].arg
            for node in ast.walk(post_init):
                if node is post_init:
                    continue
                targets = []
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif isinstance(node, ast.AugAssign):
                    targets = [node.target]
                for target in targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == self_name
                    ):
                        findings.append(
                            Finding(
                                path=path,
                                line=node.lineno,
                                col=node.col_offset,
                                code=self.code,
                                message=(
                                    f"`{self_name}.{target.attr} = ...` inside "
                                    f"`{cls.name}.__post_init__` raises FrozenInstanceError - "
                                    f"`{cls.name}` is a frozen dataclass, and frozen blocks "
                                    f"assignment even from its own __post_init__. Use "
                                    f"object.__setattr__({self_name}, '{target.attr}', ...) instead."
                                ),
                            )
                        )
        return findings
