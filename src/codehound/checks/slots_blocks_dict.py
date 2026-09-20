"""CH054 - a class defines ``__slots__`` (without ``__dict__`` in it) but
also does something that needs a per-instance ``__dict__`` anyway.

``__slots__`` exists specifically to skip giving instances a ``__dict__``.
Two common things silently assume one exists anyway, and both were verified
directly: reading ``self.__dict__`` raises ``AttributeError: ... object has
no attribute '__dict__'`` on every access, and a ``@functools.cached_property``
raises ``TypeError: No '__dict__' attribute on '...' instance to cache
'...' property`` - not at class definition, not at ``__init__``, but the
first time that specific property is *read*, which is exactly the kind of
path that's easy to leave unexercised until production.

Only fires when ``__slots__`` is a literal collection of names that does not
itself include ``"__dict__"`` - a class that deliberately adds
``"__dict__"`` to its slots gets a dict back and is unaffected by either
problem. Also only fires on a class with no base class (or only ``object``):
verified directly that a class inheriting from an *unslotted* base still
gets a real ``__dict__`` despite declaring its own ``__slots__``, since
``__dict__`` availability depends on the whole MRO, not just one class in
it - and this check can't see what an imported base class does. Also skips
a `self.__dict__` access already guarded by `hasattr(self, '__dict__')` -
found for real in pydantic's own base ``__repr_args__``, the correct,
defensive way for a shared base class to handle subclasses that may or may
not add ``__dict__`` back via their own, different ``__slots__``.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _slots_literal_names(cls: ast.ClassDef) -> list[str] | None:
    for stmt in cls.body:
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.targets[0].id == "__slots__"
        ):
            value = stmt.value
            if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
                names = []
                for elt in value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.append(elt.value)
                    else:
                        return None  # a non-literal element - can't be sure, skip
                return names
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return [value.value]
    return None


def _has_cached_property(cls: ast.ClassDef) -> ast.expr | None:
    for stmt in cls.body:
        if not isinstance(stmt, ast.FunctionDef):
            continue
        for dec in stmt.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(target, ast.Name) and target.id == "cached_property":
                return dec
            if isinstance(target, ast.Attribute) and target.attr == "cached_property":
                return dec
    return None


def _has_only_object_or_no_base(cls: ast.ClassDef) -> bool:
    if not cls.bases:
        return True
    return len(cls.bases) == 1 and isinstance(cls.bases[0], ast.Name) and cls.bases[0].id == "object"


def _is_hasattr_dict_guard(test: ast.expr) -> bool:
    """`hasattr(self, '__dict__')`, possibly `and`-chained with other
    conditions - the correct, defensive way to handle a base class whose
    subclasses may or may not add `__dict__` back via their own `__slots__`."""
    if isinstance(test, ast.BoolOp):
        return any(_is_hasattr_dict_guard(v) for v in test.values)
    return (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == "hasattr"
        and len(test.args) == 2
        and isinstance(test.args[0], ast.Name)
        and test.args[0].id == "self"
        and isinstance(test.args[1], ast.Constant)
        and test.args[1].value == "__dict__"
    )


def _is_guarded_by_hasattr(node: ast.AST, parents: dict) -> bool:
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if isinstance(p, ast.If) and cur in p.body and _is_hasattr_dict_guard(p.test):
            return True
        if isinstance(p, ast.ClassDef):
            return False
        cur = p
    return False


def _find_self_dict_access(cls: ast.ClassDef, parents: dict) -> ast.Attribute | None:
    for node in ast.walk(cls):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "__dict__"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and not _is_guarded_by_hasattr(node, parents)
        ):
            return node
    return None


class SlotsBlocksDict(Check):
    code = "CH054"
    name = "slots-blocks-dict"
    description = "A class with __slots__ (no __dict__) also relies on a per-instance __dict__ somewhere."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if not _has_only_object_or_no_base(cls):
                continue
            slots = _slots_literal_names(cls)
            if slots is None or "__dict__" in slots:
                continue

            dict_access = _find_self_dict_access(cls, parents)
            if dict_access is not None:
                findings.append(
                    Finding(
                        path=path,
                        line=dict_access.lineno,
                        col=dict_access.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}` defines `__slots__` without `__dict__`, but this "
                            f"reads `self.__dict__` - that raises `AttributeError` on every "
                            f"call, since a slotted instance has no `__dict__` to return."
                        ),
                    )
                )

            cached_prop = _has_cached_property(cls)
            if cached_prop is not None:
                findings.append(
                    Finding(
                        path=path,
                        line=cached_prop.lineno,
                        col=cached_prop.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}` defines `__slots__` without `__dict__`, but "
                            f"`@cached_property` needs one to store its cached value - this "
                            f"raises `TypeError` the first time the property is read, not at "
                            f"class definition or `__init__`."
                        ),
                    )
                )
        return findings
