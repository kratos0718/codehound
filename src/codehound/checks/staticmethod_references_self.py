"""CH049 - a ``@staticmethod`` whose body still refers to ``self``/``cls``.

A `@staticmethod` gets no implicit first argument at all - not `self`,
not `cls` - so a name lookup for `self` inside one only succeeds if
something named `self` happens to exist in an enclosing scope (rare)
or a module global (rarer still). Verified directly:

    class C:
        @staticmethod
        def method(x):
            return self.value + x

    C.method(1)   # NameError: name 'self' is not defined

The usual story: a method got decorated `@staticmethod` - or the
decorator was left over from copy-pasting a sibling method - without
noticing (or without updating) a body that still leans on instance or
class state. It's caught the moment that code path actually runs, but
"the moment that code path actually runs" is exactly the gap a static
analyzer closes - this crashes on every call, but only once someone
calls it.

Flags a `@staticmethod`-decorated method whose body contains a bare
`Name` reference to `self`/`cls` that isn't itself a parameter and has
no *other* local binding anywhere in the method - not just a
parameter. The first corpus scan found three real, distinct shapes
that all needed this to not be a false positive: vllm's
`create_from_handle` does `self = MessageQueue.__new__(MessageQueue)`
as the very first line of the static factory method, a well-known
"manually construct the instance" idiom, so every later `self.x = ...`
is completely ordinary; litellm's `utils.py` assigns `cls = type(resolved)`
partway through an unrelated static method, reusing the name for an
ordinary local variable; agno's `bedrock.py` reads `cls` only inside a
set comprehension's own `for cls in type(client).__mro__`, which is
Python 3's own separate comprehension scope, not the enclosing
method's. All three bind the name to *something* before or independent
of any read - the crash this check exists to catch only happens when
the name is read without ever being bound at all, anywhere in the
method's own scope.

A second corpus scan, run across a wider set of frameworks, found two
more real false positives, both about scope in ways the first pass
didn't account for: celery's `test_app.py` has
`@staticmethod` / `@self.app.task(shared=False)` stacked on the same
function - `self` there is in the *decorator expression*, which is
evaluated in the enclosing test method's scope before `@staticmethod`
ever applies, not inside the static method's own body. pytest's
`pytester.py` defines a whole class - and a `@staticmethod` on it -
*inside* another method, and that nested method's body reads `self`,
which resolves via an ordinary closure to the *outer* method's `self`
(verified directly: a class defined inside a method, with a
`@staticmethod` reading `self`, correctly returns the outer instance's
attribute - Python's closure rules don't care that `@staticmethod`
was applied). Fixed by only scanning `node.body` for suspect names
(never the decorator list), and by skipping entirely when the
`@staticmethod`'s own class is itself nested inside a function -
too much real closure ambiguity to guess at safely.

Only checks references whose nearest enclosing function is the static
method itself, not a `def`/`lambda` nested inside it - a nested helper
that binds its own `self`/`cls` parameter is unambiguously fine, and
reasoning about one that doesn't needs more than this check is willing
to guess at.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_class, enclosing_function

_SUSPECT_NAMES = {"self", "cls"}


def _param_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    args = func.args
    names = {a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs)}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return names


def _is_staticmethod(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in func.decorator_list)


def _class_is_locally_defined(func: ast.FunctionDef | ast.AsyncFunctionDef, parents: dict) -> bool:
    """True if the class containing `func` is itself nested inside a
    function - its methods can then legitimately close over that
    outer function's own variables, including ones named self/cls."""
    cls = enclosing_class(func, parents)
    return cls is not None and enclosing_function(cls, parents) is not None


def _has_local_binding(node: ast.AST, name: str) -> bool:
    """True if `name` is bound anywhere in `node`'s own scope - a plain
    assignment, a for-loop target, a comprehension's own generator
    target, a with-as, and so on - not counting a further-nested
    function/class/lambda, which is a separate scope."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store) and child.id == name:
            return True
        if _has_local_binding(child, name):
            return True
    return False


class StaticmethodReferencesSelf(Check):
    code = "CH049"
    name = "staticmethod-references-self"
    description = "A @staticmethod body references self/cls, which was never bound to anything - crashes with NameError on every call."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _is_staticmethod(node):
                continue
            if _class_is_locally_defined(node, parents):
                continue
            params = _param_names(node)
            names_to_check = _SUSPECT_NAMES - params
            names_to_check = {n for n in names_to_check if not any(_has_local_binding(stmt, n) for stmt in node.body)}
            if not names_to_check:
                continue
            reported: set[str] = set()
            body_nodes = [n for stmt in node.body for n in ast.walk(stmt)]
            for inner in body_nodes:
                if not (isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Load) and inner.id in names_to_check):
                    continue
                if enclosing_function(inner, parents) is not node:
                    continue  # bound by a nested function's own scope - not this method's problem
                if inner.id in reported:
                    continue
                reported.add(inner.id)
                findings.append(
                    Finding(
                        path=path,
                        line=inner.lineno,
                        col=inner.col_offset,
                        code=self.code,
                        message=(
                            f"`{inner.id}` is read here, but `@staticmethod` methods get no "
                            f"implicit first argument - `{inner.id}` was never bound to "
                            f"anything, so this raises `NameError` on every call."
                        ),
                    )
                )
        return findings
