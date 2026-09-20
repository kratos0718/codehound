"""CH057 - a generator/``map``/``filter``/``zip`` result is consumed twice.

Verified directly: ``gen = (x for x in range(5)); list(gen); list(gen)`` -
the second call returns ``[]``, silently, no error. A generator expression
(and ``map``/``filter``/``zip``, which are the same one-pass-iterator
protocol) is exhausted the first time something actually walks it to
completion; every later consumer gets nothing, because there is nothing
left to give. Unlike a list or tuple, nothing about the object's type
signals this - it prints, indexes into an error the same way, and only
misbehaves the moment a second consumer expects it to still hold data.

Only fires when the *same name*, bound once from a generator
expression/``map``/``filter``/``zip`` call and never reassigned in between,
is passed as the sole argument to two different "runs the whole iterator"
calls (``list``, ``tuple``, ``set``, ``sorted``, ``sum``, ``max``, ``min``)
or used as a `for` loop's iterable twice - reading it lazily one item at a
time twice (e.g. two separate ``next(gen)`` calls) is completely normal and
not what this looks for.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_TERMINAL_FUNCS = {"list", "tuple", "set", "sorted", "sum", "max", "min"}
_ITERATOR_FACTORY_FUNCS = {"map", "filter", "zip"}


def _is_iterator_factory(node: ast.expr) -> bool:
    if isinstance(node, ast.GeneratorExp):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ITERATOR_FACTORY_FUNCS


def _consumption_sites(body: list[ast.stmt], name: str) -> list[ast.AST]:
    sites: list[ast.AST] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _TERMINAL_FUNCS
                and len(node.args) >= 1
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == name
            ):
                sites.append(node)
            elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.iter, ast.Name) and node.iter.id == name:
                sites.append(node)
    return sites


def _is_reassigned_between(body: list[ast.stmt], name: str, after_lineno: int, before_lineno: int) -> bool:
    for stmt in body:
        for node in ast.walk(stmt):
            if not hasattr(node, "lineno") or not (after_lineno < node.lineno < before_lineno):
                continue
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets
            ):
                return True
            if isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name) and node.target.id == name:
                return True
    return False


class ReusedExhaustedIterator(Check):
    code = "CH057"
    name = "reused-exhausted-iterator"
    description = "A generator/map/filter/zip result is fully consumed more than once; later consumers get nothing."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for stmt in func.body:
                if not (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and _is_iterator_factory(stmt.value)
                ):
                    continue
                name = stmt.targets[0].id
                sites = _consumption_sites(func.body, name)
                sites = [s for s in sites if s.lineno > stmt.lineno]
                for prev, cur in zip(sites, sites[1:]):
                    if _is_reassigned_between(func.body, name, prev.lineno, cur.lineno):
                        continue
                    findings.append(
                        Finding(
                            path=path,
                            line=cur.lineno,
                            col=cur.col_offset,
                            code=self.code,
                            message=(
                                f"`{name}` was already fully consumed at line {prev.lineno} - "
                                f"a generator/map/filter/zip is a one-pass iterator, so this "
                                f"second use gets nothing left to give."
                            ),
                        )
                    )
        return findings
