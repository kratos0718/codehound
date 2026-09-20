"""CH096 - a class defines ``__post_init__``, has no ``@dataclass``
decorator, no *other* decorator, and no base class.

Verified directly:

    class Foo:
        def __init__(self): pass
        def __post_init__(self):
            self.ready = True

    f = Foo()
    hasattr(f, "ready")   # False - __post_init__ never ran

`__post_init__` isn't a real Python dunder the interpreter calls on its
own - it's a convention: `@dataclass`'s generated `__init__` explicitly
calls `self.__post_init__()` at the end, if the method exists. A plain,
hand-written `__init__` has no such call built in.

But `@dataclass` isn't the only place this convention lives - the first
corpus pass found it independently reinvented, undecorated but for a
custom name, in real code: vllm's own `@config` decorator (not literally
named `dataclass`) builds a pydantic dataclass internally
(`dataclass(cls, config=merged_config)`), and transformers' base
`PreTrainedConfig.__init__` calls `self.__post_init__(**kwargs)` itself
as a documented hook, with no decorator involved at all - meaning a
class inheriting from it picks up that call for free. Neither is visible
from a single file, so requiring "no `@dataclass` decorator" alone
produced 615 false positives across two unrelated real code patterns.

Narrowed to the only case that's actually airtight: the class has *no*
decorator at all (any decorator might be doing something like vllm's
`@config`) and *no* base class at all (any base might implement the same
hook transformers' `PreTrainedConfig` does) - a genuinely bare,
undecorated `class Foo:` is the only shape where nothing else in the
file could possibly be calling `__post_init__` for it.

One more real shape from the corpus: a bare, undecorated base class can
still have its own `__post_init__` legitimately called if some *other*
class in the same file subclasses it *and* is itself `@dataclass`-decorated
- HuggingFace `datasets`' `_ArrayXD` defines `__post_init__` with no
decorator and no base of its own, but `Array2D(_ArrayXD)`,
`Array3D(_ArrayXD)`, etc. are all `@dataclass`-decorated, and inherit the
method (and the call to it) for free. Skipped by checking every other
class in the file for `cls.name` in its bases plus a dataclass-like
decorator, before flagging.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_dataclass_like_decorator(dec: ast.expr) -> bool:
    target = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(target, ast.Name):
        return target.id == "dataclass"
    if isinstance(target, ast.Attribute):
        return target.attr == "dataclass"
    return False


def _has_dataclass_subclass(cls_name: str, all_classes: list[ast.ClassDef]) -> bool:
    for other in all_classes:
        base_names = {b.id for b in other.bases if isinstance(b, ast.Name)}
        if cls_name in base_names and any(_is_dataclass_like_decorator(d) for d in other.decorator_list):
            return True
    return False


class PostInitOnNonDataclass(Check):
    code = "CH096"
    name = "post-init-on-non-dataclass"
    description = "__post_init__ is defined on a plain class with no decorator and no base (and no dataclass subclass) - nothing calls it, it's dead code."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        all_classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        for cls in all_classes:
            if cls.decorator_list or cls.bases:
                continue
            if _has_dataclass_subclass(cls.name, all_classes):
                continue
            for stmt in cls.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "__post_init__":
                    findings.append(
                        Finding(
                            path=path,
                            line=stmt.lineno,
                            col=stmt.col_offset,
                            code=self.code,
                            message=(
                                f"`{cls.name}.__post_init__` is defined, but `{cls.name}` has no "
                                f"decorator and no base class - nothing generates an __init__ "
                                f"that would call it, so this method is silently dead code."
                            ),
                        )
                    )
        return findings
