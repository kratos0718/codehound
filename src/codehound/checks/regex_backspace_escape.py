"""CH061 - a regex pattern string contains a literal backspace character,
almost always an un-raw ``\\b`` that was meant to be a word-boundary escape.

Verified directly: a raw string ``r"\\bword\\b"`` parses to the two
characters ``\\`` and ``b`` around ``word``, which the regex engine itself
then interprets as a word-boundary assertion. Without the ``r`` prefix,
Python's own string escape processing runs first and turns ``\\b`` into an
actual backspace byte (``\\x08``) *before* the regex engine ever sees it -
`re.search("\\bword\\b", "a word here")` returns `None`, silently failing
to match anything, while the raw version matches correctly. This is the
one escape sequence where Python's own processing and what a regex author
almost always means genuinely diverge - `\\n`, `\\t`, `\\r` and friends
happen to produce the same practical match either way, and `\\d`, `\\s`,
`\\w` aren't real Python escapes at all, so flake8's own invalid-escape
warning (W605) never fires here either: `\\b` **is** a valid, recognized
Python escape, just not the one a regex ever wants.

Only fires on a call to ``re.<func>(...)`` specifically (the receiver must
be a bare name ``re``) - matching on the function name alone would also
catch the unrelated builtin ``compile()`` (compiling source code, not a
regex) and any other object's own ``.match()``/``.search()`` method.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_RE_FUNCS = {"compile", "match", "search", "fullmatch", "split", "sub", "subn", "findall", "finditer"}


class RegexBackspaceEscape(Check):
    code = "CH061"
    name = "regex-backspace-escape"
    description = "A regex pattern string contains a literal backspace byte - almost always an un-raw \\b."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_re_call = (
                isinstance(func, ast.Attribute)
                and func.attr in _RE_FUNCS
                and isinstance(func.value, ast.Name)
                and func.value.id == "re"
            )
            if not is_re_call or not node.args:
                continue
            pattern_arg = node.args[0]
            if (
                isinstance(pattern_arg, ast.Constant)
                and isinstance(pattern_arg.value, str)
                and "\x08" in pattern_arg.value
            ):
                findings.append(
                    Finding(
                        path=path,
                        line=pattern_arg.lineno,
                        col=pattern_arg.col_offset,
                        code=self.code,
                        message=(
                            "This pattern contains a literal backspace character - almost "
                            "certainly `\\b` written without an `r''` prefix, so Python turned "
                            "it into a backspace byte before the regex engine ever saw it, "
                            "silently breaking the word-boundary match. Use a raw string: "
                            "r'...\\b...'."
                        ),
                    )
                )
        return findings
