"""CH033 - ``.strip()``/``.lstrip()``/``.rstrip()`` called with a multi-character string.

`str.strip(chars)` doesn't remove a substring - `chars` is a *set* of
characters, stripped one at a time from each end for as long as the
next character matches something in the set. Verified directly, in the
shape this actually bites people in:

    "report.txt".strip(".txt")   # 'repor'  - not 'report'
    "test.txt".strip(".txt")     # 'es'     - not 'test'

Both look like "strip the `.txt` suffix," and both are wrong: the
trailing `t` in "report" and the leading `t` in "test" are themselves in
the character set `{'.', 't', 'x'}`, so they get eaten too. This is
flake8-bugbear's B005, included here because it's exactly the kind of
subtle, easy-to-write, hard-to-notice correctness bug this project
exists to catch - the code runs, returns a string, and looks plausible
at a glance.

Scanning ~30 real frameworks turned up over a hundred multi-character
`.strip()` calls, and the overwhelming majority were deliberate,
correct uses of the character-*set* semantics: `.strip('\r\n')` to
absorb either line-ending convention, `.strip('[]')`/`.strip('()')` to
peel matching brackets, `.strip('\'"')` to drop either quote style,
`.lstrip('│ ├└─')` to strip box-drawing tree glyphs.
None of those are "misread as a substring" mistakes - a reader who
sees a bag of punctuation or whitespace correctly reads it as a set.
The real mistakes only showed up when the argument contained a letter
or digit: `.lstrip('data:')` (the SSE "data: " prefix), `.strip('/v1')`
(an API version suffix), `.strip('THREAD#')`/`.strip('STEP#')` (DynamoDB
key prefixes), `.rstrip('/n')` (almost certainly a typo for `'\n'`) -
those really do read like someone meant a prefix or suffix and reached
for the wrong method.

So this only flags a multi-character argument that contains at least
one letter or digit, and isn't just the same character repeated
(`.strip('```')` strips one character, backtick, no matter how many
times it appears in the argument - no charset/substring ambiguity to
get wrong either).
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_STRIP_METHODS = {"strip", "lstrip", "rstrip"}


class StripMultichar(Check):
    code = "CH033"
    name = "strip-multichar-argument"
    description = "str.strip()/.lstrip()/.rstrip() with a multi-character argument strips a character set, not a substring."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _STRIP_METHODS
                and len(node.args) == 1
                and not node.keywords
            ):
                continue
            arg = node.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str) and len(arg.value) > 1):
                continue
            chars = arg.value
            if len(set(chars)) == 1:
                continue
            if not any(c.isalnum() for c in chars):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self.code,
                    message=(
                        f"`.{node.func.attr}({arg.value!r})` strips any of these characters "
                        f"from each end, not the substring `{arg.value!r}` - "
                        f"`{arg.value[0]!r}{arg.value[-1]!r}` and every character in between are "
                        f"each removed independently for as long as they keep matching."
                    ),
                )
            )
        return findings
