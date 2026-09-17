"""CH011 - ``@lru_cache``/``@cache`` on an instance method leaks every instance.

``functools.lru_cache`` (and its 3.9+ shorthand ``functools.cache``) memoizes
by keying on the *arguments*, including ``self`` for a bound method. The
cache is a module-level structure attached to the function object, which
outlives any particular instance - so every instance that ever calls the
cached method stays referenced by the cache **forever**, even after every
other reference to it is gone. This is a real, well-documented memory leak
(the cache silently keeps the whole object graph reachable from that
instance alive), not a style nit.

Only fires on a method - a plain module-level function decorated the same
way is exactly what ``lru_cache`` is for, and caches correctly with no
leak (nothing but the arguments themselves are held).

Also doesn't fire on a *frozen* value class (a stdlib ``@dataclass(frozen=
True)`` or a pydantic model with ``model_config = ConfigDict(frozen=True)``
/ ``class Config: frozen = True``). A frozen class is hashable and equal by
its field values, not by identity - verified directly: two separately
constructed instances with the same field values hash equal, and a second,
distinct instance's call is served straight from the first instance's
cache entry without ever being inserted itself (dspy's `Image.format()`,
checked this way, turned out to be exactly this - real, bounded-by-value
memoization on an immutable type, not a leak). The cache still only ever
holds as many distinct instances as there are distinct field-value
combinations seen, capped at `maxsize`, which is the same bound an
equivalent free function cached by value would have.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_CACHE_DECORATOR_NAMES = {"lru_cache", "cache"}


def _is_cache_decorator(node: ast.expr) -> bool:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id in _CACHE_DECORATOR_NAMES
    if isinstance(target, ast.Attribute):
        return target.attr in _CACHE_DECORATOR_NAMES
    return False


def _is_frozen_dataclass(decorators: list[ast.expr]) -> bool:
    for d in decorators:
        if not isinstance(d, ast.Call):
            continue
        target = d.func
        name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
        if name != "dataclass":
            continue
        for kw in d.keywords:
            if kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _is_frozen_pydantic_model(cls: ast.ClassDef) -> bool:
    for stmt in cls.body:
        # model_config = ConfigDict(..., frozen=True, ...) or {"frozen": True}
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "model_config"
        ):
            value = stmt.value
            if isinstance(value, ast.Call):
                for kw in value.keywords:
                    if kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                        return True
            elif isinstance(value, ast.Dict):
                for k, v in zip(value.keys, value.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "frozen"
                        and isinstance(v, ast.Constant)
                        and v.value is True
                    ):
                        return True
        # Old-style pydantic v1: `class Config: frozen = True`
        if isinstance(stmt, ast.ClassDef) and stmt.name == "Config":
            for inner in stmt.body:
                if (
                    isinstance(inner, ast.Assign)
                    and len(inner.targets) == 1
                    and isinstance(inner.targets[0], ast.Name)
                    and inner.targets[0].id == "frozen"
                    and isinstance(inner.value, ast.Constant)
                    and inner.value.value is True
                ):
                    return True
    return False


def _is_frozen_value_class(cls: ast.ClassDef) -> bool:
    return _is_frozen_dataclass(cls.decorator_list) or _is_frozen_pydantic_model(cls)


def _is_static_or_classmethod(decorators: list[ast.expr]) -> bool:
    for d in decorators:
        target = d.func if isinstance(d, ast.Call) else d
        name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", None)
        if name in ("staticmethod", "classmethod"):
            return True
    return False


class LruCacheOnMethod(Check):
    code = "CH011"
    name = "lru-cache-on-method"
    description = "@lru_cache/@cache on an instance method keeps every instance alive forever."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parent = parents.get(id(node))
            if not isinstance(parent, ast.ClassDef):
                continue
            if _is_static_or_classmethod(node.decorator_list):
                continue
            if _is_frozen_value_class(parent):
                continue
            if not node.args.args or node.args.args[0].arg not in ("self",):
                continue
            for dec in node.decorator_list:
                if not _is_cache_decorator(dec):
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`{node.name}` is a cached instance method - the cache holds a "
                            f"strong reference to `self` for the process lifetime, keeping "
                            f"every instance that ever called it alive. Cache on a module-level "
                            f"function, or key on something that isn't `self`."
                        ),
                    )
                )
                break
        return findings
