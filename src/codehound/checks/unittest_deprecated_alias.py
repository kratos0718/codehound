"""CH024 - deprecated ``unittest.TestCase`` method aliases, removed in Python 3.12.

`assertEquals`, `failUnless`, and a dozen other camelCase/legacy aliases
dated back to `unittest`'s original `PyUnit`-era API, deprecated for
over a decade, then removed outright in Python 3.12 - `AttributeError`
on `self.assertEquals(...)` the moment the test runs, not something a
type checker catches ahead of time.

Only fires on a `self.<alias>(...)` call - these names are distinctive
enough (nobody else names a method `assertEquals` or `failUnlessRaises`)
that the same name-collision risk CH018 guards against for `Task`
doesn't meaningfully apply here.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_ALIAS_TO_REPLACEMENT: dict[str, str] = {
    "assertAlmostEquals": "assertAlmostEqual",
    "assertEquals": "assertEqual",
    "assertNotAlmostEquals": "assertNotAlmostEqual",
    "assertNotEquals": "assertNotEqual",
    "assertNotRegexpMatches": "assertNotRegex",
    "assertRaisesRegexp": "assertRaisesRegex",
    "assertRegexpMatches": "assertRegex",
    "assert_": "assertTrue",
    "failIf": "assertFalse",
    "failIfAlmostEqual": "assertNotAlmostEqual",
    "failIfEqual": "assertNotEqual",
    "failUnless": "assertTrue",
    "failUnlessAlmostEqual": "assertAlmostEqual",
    "failUnlessEqual": "assertEqual",
    "failUnlessRaises": "assertRaises",
}


class UnittestDeprecatedAlias(Check):
    code = "CH024"
    name = "unittest-deprecated-alias"
    description = "unittest.TestCase alias (assertEquals, failUnless, etc) removed in Python 3.12."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
                and node.func.attr in _ALIAS_TO_REPLACEMENT
            ):
                replacement = _ALIAS_TO_REPLACEMENT[node.func.attr]
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message=(
                            f"`self.{node.func.attr}(...)` - removed in Python 3.12; use "
                            f"`self.{replacement}(...)`."
                        ),
                    )
                )
        return findings
