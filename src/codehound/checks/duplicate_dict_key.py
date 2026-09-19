"""CH045 - a dict literal with the same key written twice.

A dict literal builds its entries left to right, and a later entry
with an equal key silently overwrites the earlier one - `{"a": 1, "a":
2}` doesn't error, it just quietly becomes `{"a": 2}`. Verified
directly:

    {"a": 1, "b": 2, "a": 3}   # {'a': 3, 'b': 2} - the first "a": 1 is gone

Almost always one of two mistakes: a copy-paste of a whole key/value
pair where only the value should have changed, or a key that was
*meant* to be different and has a typo. Either way, an earlier entry
just disappears with no error, no warning - the dict has fewer visible
signs that a mistake happened than a duplicate anywhere else in the
same source would.

Matches by actual runtime equality for simple, hashable, statically
comparable constants (str/bytes/int/float/complex/bool/None/tuple of
those) - `1`, `1.0`, and `True` really do collide as the same dict
key, so this check treats them the same way. Doesn't resolve names or
arbitrary expressions, since two different-looking expressions could
still evaluate to an equal key (or an identical-looking one could
evaluate differently), and this project's whole approach is matching
what the AST can actually prove, not what it can guess.
"""

from __future__ import annotations

import ast

from codehound.core import UNRESOLVED, Check, Finding, literal_value


class DuplicateDictKey(Check):
    code = "CH045"
    name = "duplicate-dict-key"
    description = "A dict literal has the same key twice - the earlier entry is silently overwritten."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            seen: dict[tuple, ast.expr] = {}
            for key in node.keys:
                if key is None:  # a **spread entry - no literal key to compare
                    continue
                comparable = literal_value(key)
                if comparable is UNRESOLVED:
                    continue
                if comparable in seen:
                    findings.append(
                        Finding(
                            path=path,
                            line=key.lineno,
                            col=key.col_offset,
                            code=self.code,
                            message=(
                                "this key already appeared earlier in the same dict literal - "
                                "that earlier entry is silently overwritten, not merged or "
                                "combined."
                            ),
                        )
                    )
                seen[comparable] = key
        return findings
