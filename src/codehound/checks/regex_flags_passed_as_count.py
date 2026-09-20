"""CH088 - a regex flag (``re.IGNORECASE``, ``re.MULTILINE``, ...) is
passed as a positional argument that ``re.sub``/``re.subn``/``re.split``
actually reads as ``count``/``maxsplit``.

Verified directly:

    re.sub("hello", "hi", text, re.IGNORECASE)
    # re.IGNORECASE == 2, silently becomes count=2 - flags stays 0
    # case-insensitive matching never happens; at most 2 replacements occur

    re.split("x", text, re.IGNORECASE)
    # becomes maxsplit=2 - the string is split at most twice, case-sensitively

`re.sub`/`re.subn`'s signature is `(pattern, repl, string, count=0,
flags=0)`; `re.split`'s is `(pattern, string, maxsplit=0, flags=0)`. A
flag constant passed positionally in the count/maxsplit slot is a valid
int (the flag values are small integers), so nothing raises - the call
just silently does the wrong thing: intended case-insensitivity (or
whatever flag was meant) never applies, and replacement/splitting stops
early at whatever number the flag's integer value happens to be.

Only fires when the flag-shaped argument (a `re.X` attribute, `re.X |
re.Y`, or a bare `IGNORECASE`/`I`/etc. name) lands in exactly the
count/maxsplit position with no explicit `flags=` keyword already
present.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

_FLAG_NAMES = {
    "IGNORECASE",
    "I",
    "MULTILINE",
    "M",
    "DOTALL",
    "S",
    "VERBOSE",
    "X",
    "ASCII",
    "A",
    "UNICODE",
    "U",
    "LOCALE",
    "L",
    "TEMPLATE",
    "T",
    "NOFLAG",
}


def _is_flag_name(node: ast.expr) -> bool:
    if isinstance(node, ast.Attribute):
        return node.attr in _FLAG_NAMES
    if isinstance(node, ast.Name):
        return node.id in _FLAG_NAMES
    return False


def _looks_like_flags(node: ast.expr) -> bool:
    if _is_flag_name(node):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _looks_like_flags(node.left) and (_is_flag_name(node.right) or _looks_like_flags(node.right))
    return False


class RegexFlagsPassedAsCount(Check):
    code = "CH088"
    name = "regex-flags-passed-as-count"
    description = "A re.X flag passed positionally to re.sub/subn/split lands in the count/maxsplit slot instead of flags - silently ignored."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "re"):
                continue
            if any(kw.arg == "flags" for kw in node.keywords):
                continue
            if func.attr in ("sub", "subn") and len(node.args) == 4:
                bad_arg = node.args[3]
                slot, position = "count", "4th"
            elif func.attr == "split" and len(node.args) == 3:
                bad_arg = node.args[2]
                slot, position = "maxsplit", "3rd"
            else:
                continue
            if not _looks_like_flags(bad_arg):
                continue
            findings.append(
                Finding(
                    path=path,
                    line=bad_arg.lineno,
                    col=bad_arg.col_offset,
                    code=self.code,
                    message=(
                        f"re.{func.attr}()'s {position} positional slot here is `{slot}`, not "
                        f"`flags` - this flag-shaped argument silently becomes {slot}=<flag's "
                        f"integer value> instead of applying the flag. Pass it as flags=... "
                        f"explicitly."
                    ),
                )
            )
        return findings
