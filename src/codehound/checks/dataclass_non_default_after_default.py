"""CH079 - a ``@dataclass`` field with no default is declared after one
that has a default.

Verified directly:

    @dataclass
    class D:
        x: int = 0
        y: int
    # TypeError: non-default argument 'y' follows default argument

`@dataclass` builds `__init__`'s parameter list straight from the class
body's field order, and Python doesn't allow a required positional
parameter after one with a default - so this raises the moment the class
body is executed (import time), not when it's instantiated.

A field counts as "has a default" if its `AnnAssign` has a value at all,
*except* a bare `field(...)` call with neither `default=` nor
`default_factory=` - that spells `= field(...)` but is still a required
field, so it doesn't reset the ordering requirement (and doesn't trigger
it either). A field marked `field(kw_only=True)` is passed by keyword
only, exempting it from positional ordering entirely, so encountering one
resets tracking for the rest of the class body. `@dataclass(kw_only=True)`
on the class itself makes *every* field keyword-only, found for real in
vllm's `ServeContext` - the whole class is skipped in that case, since the
ordering constraint never applies to any of its fields.

Three more exemptions, all found for real in the corpus: `field(init=False)`
takes a field out of `__init__`'s parameter list entirely (huggingface_hub's
`_BucketCopyFile.mtime`, declared with no default right after one that has
one - verified directly this raises nothing, since a field excluded from
`__init__` was never part of the ordering to begin with); `@dataclass(init=False)`
on the class means no `__init__` is generated at all (pydantic-ai's
`AgentRun`), so the whole class is skipped the same way class-level
`kw_only=True` is; and a `ClassVar[...]`-annotated attribute (vllm's
tensorizer config, `_fields: ClassVar[tuple[str, ...]]` with no value,
right after several defaulted fields) isn't a dataclass field at all -
`@dataclass` explicitly skips `ClassVar` annotations when building
`__init__`, verified directly - so it's excluded from the ordering
tracking entirely, not just treated as "has no default".

A fourth: the `dataclasses.KW_ONLY` sentinel (`_: KW_ONLY`, pydantic-ai's
`BaseToolReturnPart` and others) switches every field declared *after* it
to keyword-only, the same way class-level `kw_only=True` does but
mid-class - verified directly - so once one is seen, every later field in
that class body is skipped too.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _dataclass_decorator(cls: ast.ClassDef) -> ast.expr | None:
    for dec in cls.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        is_dataclass = (isinstance(target, ast.Name) and target.id == "dataclass") or (
            isinstance(target, ast.Attribute) and target.attr == "dataclass"
        )
        if is_dataclass:
            return dec
    return None


def _is_classvar(annotation: ast.expr) -> bool:
    target = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    if isinstance(target, ast.Name):
        return target.id == "ClassVar"
    if isinstance(target, ast.Attribute):
        return target.attr == "ClassVar"
    return False


def _is_kw_only_sentinel(annotation: ast.expr) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id == "KW_ONLY"
    if isinstance(annotation, ast.Attribute):
        return annotation.attr == "KW_ONLY"
    return False


def _has_bool_kwarg(call: ast.Call, flag: str, expected: bool) -> bool:
    return any(
        kw.arg == flag and isinstance(kw.value, ast.Constant) and kw.value.value is expected for kw in call.keywords
    )


def _is_field_call(node: ast.expr) -> ast.Call | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name) and func.id == "field":
        return node
    if isinstance(func, ast.Attribute) and func.attr == "field":
        return node
    return None


def _field_status(value: ast.expr | None) -> str:
    """Returns "exempt" (kw_only or init=False), "has_default", or "required"."""
    if value is None:
        return "required"
    call = _is_field_call(value)
    if call is None:
        return "has_default"
    if _has_bool_kwarg(call, "kw_only", True) or _has_bool_kwarg(call, "init", False):
        return "exempt"
    if any(kw.arg in ("default", "default_factory") for kw in call.keywords):
        return "has_default"
    return "required"


class DataclassNonDefaultAfterDefault(Check):
    code = "CH079"
    name = "dataclass-non-default-after-default"
    description = "A dataclass field with no default follows one that has a default - raises TypeError at import time."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            deco = _dataclass_decorator(cls)
            if deco is None:
                continue
            if isinstance(deco, ast.Call) and (
                _has_bool_kwarg(deco, "kw_only", True) or _has_bool_kwarg(deco, "init", False)
            ):
                continue  # every field is keyword-only, or no __init__ is generated at all
            seen_default: ast.AnnAssign | None = None
            past_kw_only_sentinel = False
            for stmt in cls.body:
                if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
                    continue
                if _is_kw_only_sentinel(stmt.annotation):
                    past_kw_only_sentinel = True
                    continue
                if past_kw_only_sentinel:
                    continue  # everything after the KW_ONLY marker is keyword-only
                if _is_classvar(stmt.annotation):
                    continue  # not a dataclass field at all - excluded from __init__ entirely
                status = _field_status(stmt.value)
                if status == "exempt":
                    continue
                if status == "required":
                    if seen_default is not None:
                        findings.append(
                            Finding(
                                path=path,
                                line=stmt.lineno,
                                col=stmt.col_offset,
                                code=self.code,
                                message=(
                                    f"`{cls.name}.{stmt.target.id}` has no default and follows "
                                    f"`{seen_default.target.id}`, which does - @dataclass builds "
                                    f"__init__ in field order, and a required parameter can't "
                                    f"follow one with a default. Raises TypeError at import time."
                                ),
                            )
                        )
                else:
                    seen_default = stmt
        return findings
