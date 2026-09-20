"""CH087 - ``enumerate(seq, start=N)``'s index is used to re-index the
same ``seq`` inside the loop body.

Verified directly:

    items = ["a", "b", "c"]
    for i, item in enumerate(items, start=1):
        items[i]
    # i=1 -> items[1] is "b", but `item` at that point is "a" - mismatched
    # i=3 on the last iteration -> IndexError: list index out of range

`enumerate(seq, start=N)` offsets the *counter* it hands back, not the
position it reads from - `seq` is still walked 0-indexed underneath.
Using that offset counter to index back into the same sequence produces
values that don't correspond to the current iteration for every index
below the offset, and runs off the end entirely once the offset is
reached, since the true valid index range is still `0..len(seq)-1`.

Only fires when `seq` is a bare name, `start=` (or the second positional
arg) is a nonzero integer literal, and the loop body subscripts that
exact name with the loop's own index variable.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding


def _enumerate_info(node: ast.expr) -> tuple[str, int] | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    is_enumerate = (isinstance(func, ast.Name) and func.id == "enumerate") or (
        isinstance(func, ast.Attribute) and func.attr == "enumerate"
    )
    if not is_enumerate or not node.args or not isinstance(node.args[0], ast.Name):
        return None
    seq_name = node.args[0].id
    start_node = None
    if len(node.args) >= 2:
        start_node = node.args[1]
    else:
        start_node = next((kw.value for kw in node.keywords if kw.arg == "start"), None)
    if start_node is None or not isinstance(start_node, ast.Constant) or not isinstance(start_node.value, int):
        return None
    if start_node.value == 0:
        return None
    return seq_name, start_node.value


class EnumerateStartOffsetReindex(Check):
    code = "CH087"
    name = "enumerate-start-offset-reindex"
    description = "enumerate(seq, start=N) offsets the counter, not the read position - using it to index back into seq is mismatched and eventually out of range."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.For):
                continue
            info = _enumerate_info(node.iter)
            if info is None:
                continue
            seq_name, start = info
            if not isinstance(node.target, ast.Tuple) or len(node.target.elts) != 2:
                continue
            idx_target = node.target.elts[0]
            if not isinstance(idx_target, ast.Name):
                continue
            idx_name = idx_target.id
            hit = None
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if (
                        isinstance(sub, ast.Subscript)
                        and isinstance(sub.value, ast.Name)
                        and sub.value.id == seq_name
                        and isinstance(sub.slice, ast.Name)
                        and sub.slice.id == idx_name
                    ):
                        hit = sub
                        break
                if hit is not None:
                    break
            if hit is None:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=hit.lineno,
                    col=hit.col_offset,
                    code=self.code,
                    message=(
                        f"`{seq_name}[{idx_name}]` re-indexes `{seq_name}` with the counter "
                        f"from enumerate({seq_name}, start={start}) - that counter is offset "
                        f"by {start}, but `{seq_name}` is still walked 0-indexed, so this reads "
                        f"the wrong element and raises IndexError once {idx_name} reaches "
                        f"len({seq_name})."
                    ),
                )
            )
        return findings
