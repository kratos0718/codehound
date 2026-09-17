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
