"""CH084 - reading a ``defaultdict`` subscript as a condition's test
silently inserts the key.

Verified directly:

    d = defaultdict(list)
    len(d)                  # 0
    if d["missing_key"]:
        pass
    len(d)                  # 1 - the mere read created the key

`defaultdict.__getitem__` calls the factory and *stores* the result the
moment a missing key is looked up - there's no read-only access path.
Using the subscript directly as a condition (`if d[key]:`, `while
d[key]:`) reads it exactly once, for the side effect of inserting an
entry the caller may never have meant to create, with nothing marking
that it happened.

Only fires on the direct shape `if d[key]:`/`while d[key]:` (optionally
wrapped in a single `not`) where `d` was assigned from a
`defaultdict(...)` constructor call earlier in the same function or
module. `d.get(key)` and `key in d` are the read-only alternatives and
are never touched by this check.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding, enclosing_function


def _is_defaultdict_call(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "defaultdict"
    if isinstance(func, ast.Attribute):
        return func.attr == "defaultdict"
    return False


def _subscript_test(test: ast.expr) -> ast.Subscript | None:
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        test = test.operand
    if isinstance(test, ast.Subscript) and isinstance(test.value, ast.Name):
        return test
    return None


class DefaultdictReadCreatesKey(Check):
    code = "CH084"
    name = "defaultdict-read-creates-key"
    description = "A defaultdict subscript used directly as an if/while condition silently inserts the key as a side effect."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name) or not _is_defaultdict_call(node.value):
                continue
            dict_name = target.id
            scope = enclosing_function(node, parents) or tree
            for later in ast.walk(scope):
                if getattr(later, "lineno", -1) <= node.lineno:
                    continue
                if not isinstance(later, (ast.If, ast.While)):
                    continue
                sub = _subscript_test(later.test)
                if sub is None or sub.value.id != dict_name:
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=sub.lineno,
                        col=sub.col_offset,
                        code=self.code,
                        message=(
                            f"`{dict_name}` is a defaultdict; using `{dict_name}[...]` directly "
                            f"as this condition's test reads it by calling __getitem__, which "
                            f"inserts the key as a side effect if it wasn't already there. Use "
                            f"`{dict_name}.get(...)` or `... in {dict_name}` for a read-only check."
                        ),
                    )
                )
        return findings
