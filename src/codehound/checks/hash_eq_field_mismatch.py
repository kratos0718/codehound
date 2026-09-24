"""CH091 - ``__hash__`` uses a field that ``__eq__`` doesn't compare,
breaking the hash/equality contract.

Verified directly:

    class Bad:
        def __init__(self, a, b): self.a, self.b = a, b
        def __eq__(self, other): return self.a == other.a
        def __hash__(self): return hash((self.a, self.b))

    x, y = Bad(1, 2), Bad(1, 999)
    x == y            # True
    hash(x) == hash(y)  # False
    y in {x}           # False - x == y, but a dict/set can't find it

Python's data model requires that objects comparing equal have the same
hash - a set/dict relies on this to ever find an equal key at all. Here
`__eq__` only looks at `a`, but `__hash__` also mixes in `b`, so two
objects the class itself considers equal can still land in different
hash buckets - `in`, dict lookups, and deduplication all silently break
for values that are provably equal by the class's own rules.

Only fires when `__hash__`'s body is a `return hash((...))` (or
`return hash(x)`) whose tuple/expression references `self.<attr>`
attributes *directly*, with no method call and no `@property` reference
anywhere in it - a call like `hash(self.to_json_string())` (a real
corpus hit, transformers' `GenerationConfig`) could be hashing any
number of underlying fields inside that method, invisible from here, so
the whole class is skipped rather than guessing; same reasoning for
`hash(self.hash)` where `hash` is itself a `@property` (mlflow's
`EvaluationDataset`, whose `hash` property is a content-derived digest
that may well already be consistent with `__eq__`, just not provably so
from the attribute name alone). `__eq__`'s body is searched for
`self.<attr>` references anywhere inside each side of an `==` comparison
- not just a bare `self.x == other.x`, but also
`(self.a, self.b) == (other.a, other.b)` (vllm's `DeviceCapability`) and
`sorted(self.children) == sorted(other.children)` (letta's
`ParentToolRule`, comparing through a call instead of directly) - and
`self.__dict__ == other.__dict__` is recognized as covering every field
at once, skipping the class rather than treating `__dict__` as a single
named attribute. A property that's a simple `return self._x` pass-through
(semantic-kernel's `AgentId.type`/`.key`, wrapping `self._type`/`self._key`)
is resolved to the private attribute it reads, so `__eq__` comparing the
public property and `__hash__` reading the private attribute directly
are recognized as the same field instead of two different ones.
`self.__class__` inside the hash tuple (pydantic-ai's `ModelRetry`,
hashing `(self.__class__, self.message)`) is never treated as a real
field needing a matching comparison in `__eq__` - it's a type
discriminator, and any `__eq__` already establishes the equivalent via
`isinstance(other, self.__class__)` or a type check before comparing
anything else, just never spelled as `self.__class__ == other.__class__`.
And an `__eq__` that compares reflectively - `tuple(getattr(self, f.name)
for f in fields(self)) == tuple(getattr(other, f.name) for f in
fields(self))` (transformers' `SizeDict`) - is recognized the same way
`self.__dict__` is: it can't name specific fields for this check to
extract, but it's comparing all of a dataclass's fields generically, so
the class is skipped rather than guessed at. And `__hash__` references
at least one attribute `__eq__` never compares - a hash using *fewer*
fields than `__eq__` is always safe and never flagged.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _property_names(cls: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for stmt in cls.body:
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in stmt.decorator_list:
            target = dec.attr if isinstance(dec, ast.Attribute) else dec.id if isinstance(dec, ast.Name) else None
            if target in ("property", "cached_property"):
                names.add(stmt.name)
    return names


def _self_attrs_no_calls(node: ast.AST, self_name: str, properties: set[str]) -> set[str] | None:
    """Attribute names read directly off `self_name`, or None if a method
    or property is referenced anywhere in the tree (unknowable which
    underlying fields it touches)."""
    attrs: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if isinstance(n.func.value, ast.Name) and n.func.value.id == self_name:
                return None
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == self_name:
            if n.attr == "__class__":
                continue  # a type discriminator, not a data field - never needs a matching eq comparison
            if n.attr in properties:
                return None
            attrs.add(n.attr)
    return attrs


def _hash_body_attrs(method: ast.FunctionDef, self_name: str, properties: set[str]) -> set[str] | None:
    returns = [n for n in ast.walk(method) if isinstance(n, ast.Return) and n.value is not None]
    if len(returns) != 1:
        return None
    value = returns[0].value
    if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id == "hash"):
        return None
    if not value.args:
        return None
    return _self_attrs_no_calls(value.args[0], self_name, properties)


def _self_attr_name(node: ast.expr, self_name: str) -> str | None:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == self_name:
        return node.attr
    return None


def _property_passthroughs(cls: ast.ClassDef) -> dict[str, str]:
    """Map a @property's name to the single self.<attr> it directly
    returns, for properties whose entire body is `return self._x`."""
    mapping: dict[str, str] = {}
    for stmt in cls.body:
        if not isinstance(stmt, ast.FunctionDef):
            continue
        is_property = any(
            (isinstance(d, ast.Name) and d.id == "property")
            or (isinstance(d, ast.Attribute) and d.attr == "property")
            for d in stmt.decorator_list
        )
        if not is_property or not stmt.args.args:
            continue
        self_name = stmt.args.args[0].arg
        body = [s for s in stmt.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        if len(body) != 1 or not isinstance(body[0], ast.Return):
            continue
        target = _self_attr_name(body[0].value, self_name)
        if target is not None:
            mapping[stmt.name] = target
    return mapping


def _decorator_names(node: ast.FunctionDef) -> set[str]:
    names: set[str] = set()
    for dec in node.decorator_list:
        if isinstance(dec, ast.Name):
            names.add(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.add(dec.attr)
    return names


def _is_abstract_stub(method: ast.FunctionDef) -> bool:
    """An `@abstractmethod` (or bare-stub) `__eq__` with no real body.

    `return NotImplemented`/`raise NotImplementedError`/`pass`/`...` compare
    nothing by design - they're a placeholder for subclasses to override,
    not a real equality implementation with zero fields. Treating "compares
    nothing" as "compares fewer fields than __hash__" would flag every
    single subclass-must-override ABC method, regardless of what any actual
    override compares (verified against redis-py's AbstractRetry: __hash__
    is the concrete, inherited implementation; __eq__ is the abstract stub
    every real subclass overrides with a body that *does* match __hash__'s
    fields - this check can't see that override from here, so the right
    call is to skip the class rather than guess from the stub alone).
    """
    if "abstractmethod" in _decorator_names(method):
        return True
    body = [s for s in method.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    if len(body) != 1:
        return False
    stmt = body[0]
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
        return True
    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Name) and stmt.value.id == "NotImplemented":
        return True
    if isinstance(stmt, ast.Raise):
        exc = stmt.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "NotImplementedError":
            return True
        if isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True
    return False


def _is_reflective_call(node: ast.expr) -> bool:
    """A getattr(obj, name)/fields(obj) call - compares fields chosen at
    runtime, not by a literal name this check could extract."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return False
    return node.func.id in ("getattr", "fields")


def _is_hash_based_eq(method: ast.FunctionDef, self_name: str, other_name: str) -> bool:
    """`__eq__` defined as `return hash(self) == hash(other)`.

    Unusual, but self-consistent by construction: equality *is* hash
    equality here, so the two can never disagree about which fields
    matter - there's no separate field list for __eq__ to omit (real
    corpus hit: redis-py's `CacheEntry`).
    """
    body = [s for s in method.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return False
    value = body[0].value
    if not (isinstance(value, ast.Compare) and len(value.ops) == 1 and isinstance(value.ops[0], ast.Eq)):
        return False

    def _is_hash_call_on(node: ast.expr, name: str) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "hash"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == name
        )

    left, right = value.left, value.comparators[0]
    return (_is_hash_call_on(left, self_name) and _is_hash_call_on(right, other_name)) or (
        _is_hash_call_on(left, other_name) and _is_hash_call_on(right, self_name)
    )


def _eq_body_attrs(method: ast.FunctionDef, self_name: str) -> set[str] | None:
    """Attribute names __eq__ compares, or None if it compares
    self.__dict__ wholesale, or reflectively via getattr()/fields() -
    both cover every field generically, not by name this check can see.
    `is` counts alongside `==` - comparing a field by identity instead
    of equality is a deliberate, valid choice (pydantic-ai's
    `MCPToolset.client`, compared via `is` in __eq__ and `id(...)` in
    __hash__ - both intentionally identity-based, not value-based)."""
    attrs: set[str] = set()
    for cmp in ast.walk(method):
        if not isinstance(cmp, ast.Compare) or not any(isinstance(op, (ast.Eq, ast.Is)) for op in cmp.ops):
            continue
        for operand in (cmp.left, *cmp.comparators):
            if _self_attr_name(operand, self_name) == "__dict__":
                return None
            for n in ast.walk(operand):
                if _is_reflective_call(n):
                    return None
                name = _self_attr_name(n, self_name)
                if name is not None:
                    attrs.add(name)
    return attrs


class HashEqFieldMismatch(Check):
    code = "CH091"
    name = "hash-eq-field-mismatch"
    description = "__hash__ uses a field that __eq__ doesn't compare - equal objects can hash differently, breaking set/dict lookups."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            hash_method = next((s for s in cls.body if isinstance(s, ast.FunctionDef) and s.name == "__hash__"), None)
            eq_method = next((s for s in cls.body if isinstance(s, ast.FunctionDef) and s.name == "__eq__"), None)
            if hash_method is None or eq_method is None or not hash_method.args.args:
                continue
            if _is_abstract_stub(eq_method):
                continue
            self_name = hash_method.args.args[0].arg
            if eq_method.args.args and len(eq_method.args.args) > 1:
                if _is_hash_based_eq(eq_method, eq_method.args.args[0].arg, eq_method.args.args[1].arg):
                    continue
            properties = _property_names(cls)
            hash_attrs = _hash_body_attrs(hash_method, self_name, properties)
            if not hash_attrs:
                continue
            eq_attrs = _eq_body_attrs(eq_method, eq_method.args.args[0].arg if eq_method.args.args else self_name)
            if eq_attrs is None:
                continue
            passthroughs = _property_passthroughs(cls)
            eq_attrs |= {passthroughs[name] for name in eq_attrs if name in passthroughs}
            extra = hash_attrs - eq_attrs
            if not extra:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=hash_method.lineno,
                    col=hash_method.col_offset,
                    code=self.code,
                    message=(
                        f"`{cls.name}.__hash__` uses {sorted(extra)}, which `{cls.name}.__eq__` "
                        f"never compares - two instances __eq__ considers equal can hash "
                        f"differently, breaking set/dict lookups for them."
                    ),
                )
            )
        return findings
