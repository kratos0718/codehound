"""CH040 - ``pytest.raises(Exception)`` / ``self.assertRaises(Exception)`` is too broad.

`Exception` (and `BaseException`, broader still) matches almost
everything Python code actually raises - including `AssertionError`,
the exact exception a plain `assert` statement inside the block would
raise if the code under test is broken. Verified directly:

    with pytest.raises(Exception):
        assert False, "the code under test is broken"
    # the block "passes" - AssertionError IS an Exception, so
    # pytest.raises(Exception) happily catches it and the test moves on

A test written to check "does this raise a specific, known error" ends
up unable to tell that error apart from a totally unrelated assertion
failure inside the same block - the test can pass even when the code
under test is broken in a way nobody intended to test for.

This is flake8-bugbear's B017. Scoped to the context-manager form only
(`with pytest.raises(Exception):` / `with self.assertRaises(Exception):`),
not the older `self.assertRaises(Exception, callable, *args)` call
form - that form doesn't have the same "arbitrary code runs inside a
block this broadly" risk, since the callable and its arguments are
fixed at the call site, not a body that can raise from anywhere.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_TOO_BROAD_EXCEPTIONS = {"Exception", "BaseException"}
_ASSERT_RAISES_METHODS = {"assertRaises", "assertRaisesRegex"}


def _too_broad_exception_name(call: ast.Call) -> str | None:
    func = call.func
    is_pytest_raises = (
        isinstance(func, ast.Attribute)
        and func.attr == "raises"
        and isinstance(func.value, ast.Name)
        and func.value.id == "pytest"
    )
    is_assert_raises = isinstance(func, ast.Attribute) and func.attr in _ASSERT_RAISES_METHODS
    if not (is_pytest_raises or is_assert_raises):
        return None

    arg = call.args[0] if call.args else None
    if arg is None:
        for kw in call.keywords:
            if kw.arg == "expected_exception":
                arg = kw.value
                break
    if isinstance(arg, ast.Name) and arg.id in _TOO_BROAD_EXCEPTIONS:
        return arg.id
    return None


class AssertRaisesTooBroad(Check):
    code = "CH040"
    name = "assert-raises-too-broad"
    description = "pytest.raises(Exception)/self.assertRaises(Exception) also catches an AssertionError from broken code under test."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.With, ast.AsyncWith)):
                continue
            for item in node.items:
                if not isinstance(item.context_expr, ast.Call):
                    continue
                exc_name = _too_broad_exception_name(item.context_expr)
                if exc_name is None:
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=item.context_expr.lineno,
                        col=item.context_expr.col_offset,
                        code=self.code,
                        message=(
                            f"catching `{exc_name}` here also catches `AssertionError` from "
                            f"anything else inside the block - if the code under test is broken "
                            f"in an unrelated way, this still reports as a pass. Match a specific "
                            f"exception type instead."
                        ),
                    )
                )
        return findings
