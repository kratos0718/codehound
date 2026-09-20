"""CH077 - ``@abstractmethod`` on a method of a class with no base classes
and no ``ABCMeta`` metaclass does nothing.

Verified directly:

    from abc import abstractmethod
    class Base:
        @abstractmethod
        def must_impl(self): pass
    class Sub(Base):
        pass
    Sub()   # instantiates fine - no error, despite the unimplemented abstractmethod

``@abstractmethod`` is inert on its own - it's `ABCMeta.__call__` that
actually checks for unimplemented abstract methods at instantiation time
and refuses to build the instance. A class that inherits straight from
`object` (no bases at all) and doesn't pass `metaclass=ABCMeta` has no way
to get that enforcement from anywhere, so the decorator is pure
documentation: every subclass, including ones that forget to implement
the method, instantiates without complaint.

Only fires when the class has zero base classes and no `metaclass=`
keyword - a class with *any* base is left alone, since that base might
itself derive from `ABC` (invisible to a single-file AST check), which
would make the enforcement real.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _is_abstractmethod_decorator(dec: ast.expr) -> bool:
    if isinstance(dec, ast.Call):
        dec = dec.func
    if isinstance(dec, ast.Name):
        return dec.id in ("abstractmethod", "abstractproperty")
    if isinstance(dec, ast.Attribute):
        return dec.attr in ("abstractmethod", "abstractproperty")
    return False


class AbstractmethodWithoutAbc(Check):
    code = "CH077"
    name = "abstractmethod-without-abc"
    description = "@abstractmethod on a class with no base and no ABCMeta metaclass is never enforced - subclasses instantiate freely."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            if cls.bases:
                continue
            if any(kw.arg == "metaclass" for kw in cls.keywords):
                continue
            for stmt in cls.body:
                if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                deco = next((d for d in stmt.decorator_list if _is_abstractmethod_decorator(d)), None)
                if deco is None:
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=deco.lineno,
                        col=deco.col_offset,
                        code=self.code,
                        message=(
                            f"`{cls.name}.{stmt.name}` is @abstractmethod, but `{cls.name}` "
                            f"has no base class and no metaclass=ABCMeta - there is no "
                            f"mechanism enforcing it, so subclasses that never implement "
                            f"`{stmt.name}` instantiate without error."
                        ),
                    )
                )
        return findings
