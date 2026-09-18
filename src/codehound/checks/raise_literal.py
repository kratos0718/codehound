"""CH034 - ``raise`` with a literal instead of an exception instance.

`raise` accepts a `BaseException` instance or class - nothing else.
A string, number, or container literal isn't either, so it always
raises a *different* exception than the one the author wrote. Verified
directly, every shape:

    raise "some error"   # TypeError: exceptions must derive from BaseException
    raise None            # same TypeError
    raise f"boom {x}"     # same - still a str at runtime
    raise (1, 2)          # same, for a tuple literal
    raise {"error": x}    # same, for a dict literal

This is flake8-bugbear's B016, and it earns a place here for the same
reason CH025 (`is`-literal-comparison) does: the code that triggers it
reads like a deliberate, reasonable choice - `raise "config missing"`
looks like someone chose a plain string over defining a custom
exception class - and the failure mode is a second, unrelated
`TypeError` at the exact moment something has already gone wrong, which
is a uniquely bad time to discover a typo.

Zero configuration, zero false-positive risk: this isn't a style
opinion or a narrowed heuristic like CH032/CH033 - `raise <literal>`
has exactly one possible outcome in every version of Python 3, so there
is no "usually fine, occasionally not" case to guard against.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_LITERAL_NODE_TYPES = (ast.Constant, ast.JoinedStr, ast.List, ast.Dict, ast.Set, ast.Tuple)


class RaiseLiteral(Check):
    code = "CH034"
    name = "raise-literal"
    description = "raise with a literal (str/int/list/dict/...) instead of an exception instance always raises TypeError."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise) or node.exc is None:
                continue
            if not isinstance(node.exc, _LITERAL_NODE_TYPES):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        "raising a literal instead of an exception instance always fails with "
                        "`TypeError: exceptions must derive from BaseException` - wrap it in an "
                        "exception, e.g. `raise ValueError(...)`."
                    ),
                )
            )
        return findings
