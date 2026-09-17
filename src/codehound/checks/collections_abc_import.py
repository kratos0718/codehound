"""CH017 - ABCs imported straight from ``collections`` instead of ``collections.abc``.

``collections.Mapping``, ``.Sequence``, ``.Iterable``, and the other
container ABCs were accessible directly from the ``collections`` module as
a deprecated alias for years, then the alias was removed outright in
Python 3.10. Code written against an older Python that still imports them
this way raises ``ImportError`` on 3.10+ the moment the module is loaded -
not a subtle runtime bug, but a real, common source of "why won't this
install on the new Python" reports for anything with an older
dependency tree.
"""

from __future__ import annotations

import ast

from codehound.core import Check, Finding

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


class CollectionsAbcImport(Check):
    code = "CH017"
    name = "collections-abc-import"
    description = "collections.<ABC> is removed in 3.10+; import from collections.abc instead."

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        findings: list[Finding] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "collections":
                for alias in node.names:
                    if alias.name in _ABC_NAMES:
                        findings.append(
                            Finding(
                                path=path,
                                line=node.lineno,
                                col=node.col_offset,
                                code=self.code,
                                message=(
                                    f"`from collections import {alias.name}` - removed in Python "
                                    f"3.10; use `from collections.abc import {alias.name}`."
                                ),
                            )
                        )
            elif isinstance(node, ast.Attribute) and node.attr in _ABC_NAMES:
                if isinstance(node.value, ast.Name) and node.value.id == "collections":
                    findings.append(
                        Finding(
                            path=path,
                            line=node.lineno,
                            col=node.col_offset,
                            code=self.code,
                            message=(
                                f"`collections.{node.attr}` - removed in Python 3.10; use "
                                f"`collections.abc.{node.attr}`."
                            ),
                        )
                    )
        return findings
