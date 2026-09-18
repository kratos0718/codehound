"""Autofix support for a small set of checks where the rewrite is
mechanical and unambiguous.

Deliberately narrow, on purpose: only CH017 and CH004 ship a `--fix`.

- **CH017** (`collections.<ABC>` -> `collections.abc.<ABC>`) is a pure
  rename with no import-injection or semantic-shift risk - the ABC
  exists at the new location under the exact same name, always.
- **CH004** (`asyncio.get_event_loop()` -> `asyncio.get_running_loop()`)
  is only a safe rewrite *inside* an `async def` - outside one,
  `get_running_loop()` raises `RuntimeError` where `get_event_loop()`
  wouldn't (it creates/returns a loop instead), so those calls are left
  as detection-only and not touched by `--fix`.

Every other check either needs judgment calls this tool isn't in a
position to make automatically (is this "leak" actually intentional?)
or an import that may or may not already be in scope (CH003's
`datetime.now(timezone.utc)` needs `timezone` imported, and guessing
wrong there - silently injecting an import, or leaving a `NameError` -
is worse than just reporting the finding and letting a human fix it).

Edits are computed from the same AST position info the checks
themselves use (`lineno`/`col_offset`/`end_lineno`/`end_col_offset`),
converted to absolute string offsets and applied in one pass, in
reverse order so an earlier edit's offsets are never invalidated by a
later one changing the string's length ahead of it.

Known limitation: `ast`'s `col_offset` counts UTF-8 *bytes*, not
characters, for a line containing multi-byte characters - an edit on a
line with non-ASCII text before the edit point could land a column off.
This mirrors a documented quirk of the `ast` module itself, not
something specific to this file; it doesn't affect the overwhelmingly
common case of ASCII source before the edit point.
"""

from __future__ import annotations

import ast

from codehound.core import enclosing_function

FIXABLE_CODES = {"CH004", "CH017"}

_ABC_NAMES = {
    "Mapping",
    "MutableMapping",
    "Sequence",
    "MutableSequence",
    "Iterable",
    "Iterator",
    "Callable",
    "Hashable",
    "Sized",
    "Container",
    "Set",
    "MutableSet",
    "ByteString",
    "Coroutine",
    "Awaitable",
    "AsyncIterable",
    "AsyncIterator",
    "Reversible",
    "Collection",
    "Generator",
    "KeysView",
    "ItemsView",
    "ValuesView",
}

# (start_line, start_col, end_line, end_col, replacement_text)
Edit = tuple[int, int, int, int, str]


def _line_offsets(source: str) -> list[int]:
    """Absolute character offset where each 1-indexed line starts."""
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _to_offset(line_offsets: list[int], line: int, col: int) -> int:
    return line_offsets[line - 1] + col


def _collect_edits(tree: ast.AST, parents: dict) -> list[Edit]:
    edits: list[Edit] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "collections":
            if any(alias.name in _ABC_NAMES for alias in node.names):
                edits.append(
                    (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, None)
                )
        elif (
            isinstance(node, ast.Attribute)
            and node.attr in _ABC_NAMES
            and isinstance(node.value, ast.Name)
            and node.value.id == "collections"
        ):
            edits.append(
                (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset, None)
            )
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_event_loop"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "asyncio"
        ):
            fn = enclosing_function(node, parents)
            if isinstance(fn, ast.AsyncFunctionDef):
                func = node.func
                edits.append(
                    (func.lineno, func.col_offset, func.end_lineno, func.end_col_offset, "ch004")
                )
    return edits


def _apply_span_rewrite(text: str, kind: str | None) -> str:
    if kind == "ch004":
        return text.replace("get_event_loop", "get_running_loop", 1)
    # CH017: the span is exactly `from collections import ...` or
    # `collections.<ABC>` - "collections" appears exactly once in either.
    return text.replace("collections", "collections.abc", 1)


def fix_source(source: str, tree: ast.AST, parents: dict) -> tuple[str, int]:
    """Return ``(new_source, edit_count)``. ``new_source is source`` (no
    copy) when there's nothing to fix."""
    edits = _collect_edits(tree, parents)
    if not edits:
        return source, 0

    line_offsets = _line_offsets(source)
    spans = [
        (
            _to_offset(line_offsets, sl, sc),
            _to_offset(line_offsets, el, ec),
            kind,
        )
        for sl, sc, el, ec, kind in edits
    ]
    spans.sort(key=lambda s: s[0], reverse=True)

    result = source
    for start, end, kind in spans:
        original = result[start:end]
        replacement = _apply_span_rewrite(original, kind)
        result = result[:start] + replacement + result[end:]
    return result, len(spans)
