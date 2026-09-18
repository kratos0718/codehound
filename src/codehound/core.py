"""Core scanning engine: file discovery, AST parsing, the Finding/Check contract.

The design goal is that every check is a small, independently testable class that
receives a parsed AST plus a precomputed child->parent map (so checks can ask
"what is the enclosing function?" cheaply) and returns a list of Findings.
"""

from __future__ import annotations

import ast
import os
import re
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Iterator

# Below this many files, a process pool's startup cost isn't worth it -
# sequential scanning wins on small inputs (a handful of files, which is
# also exactly pre-commit's typical invocation shape).
_MIN_FILES_FOR_PARALLEL = 16


# Directories we never want to descend into. Third-party and generated code is
# not ours to fix, and test/example dirs deliberately contain "bad" patterns.
DEFAULT_SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        ".venv",
        "venv",
        ".tox",
        ".nox",
        "vendor",
        "site-packages",
        "tests",
        "test",
        "testing",
        "examples",
        "example",
        "cookbook",
        "docs",
    }
)


@dataclass(frozen=True)
class Finding:
    """A single rule violation at a specific source location."""

    path: str
    line: int
    col: int
    code: str
    message: str

    def as_text(self) -> str:
        return f"{self.path}:{self.line}:{self.col}: {self.code} {self.message}"

    def as_dict(self) -> dict:
        return {
            "path": self.path,
            "line": self.line,
            "col": self.col,
            "code": self.code,
            "message": self.message,
        }


class Check:
    """Base class for a single static-analysis rule.

    Subclasses set ``code``/``name``/``description`` and implement ``run``.
    """

    code: str = ""
    name: str = ""
    description: str = ""

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        raise NotImplementedError


# --- AST helpers shared by checks -------------------------------------------------


def build_parents(tree: ast.AST) -> dict:
    """Map ``id(child) -> parent_node`` for the whole tree.

    Python's ``ast`` does not record parents, but several checks need to walk
    upward (e.g. "is this call inside a ``with`` statement / an ``async def``?").
    """
    parents: dict = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def enclosing_function(node: ast.AST, parents: dict):
    """Return the nearest enclosing FunctionDef/AsyncFunctionDef, or None."""
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if p is None:
            return None
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return p
        cur = p
    return None


def enclosing_class(node: ast.AST, parents: dict) -> ast.ClassDef | None:
    """Return the nearest enclosing ClassDef, or None.

    Stops at the first FunctionDef/AsyncFunctionDef boundary that isn't
    itself inside the class body being searched for - i.e. this walks up
    through nested functions too, so a method's inner helper still resolves
    to the class it's defined in.
    """
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if p is None:
            return None
        if isinstance(p, ast.ClassDef):
            return p
        cur = p
    return None


def is_awaited(node: ast.AST, parents: dict) -> bool:
    """True if the call ``node`` is the direct operand of an ``await``.

    ``await client.get(...)`` does not block the event loop even though the
    receiver/attribute name might look like a synchronous library (e.g. a local
    variable also named ``requests`` that is actually an async HTTP client).
    """
    parent = parents.get(id(node))
    return isinstance(parent, ast.Await)


def inside_with_statement(node: ast.AST, parents: dict) -> bool:
    """True if ``node`` is (transitively) inside a with/async-with, stopping at
    the enclosing function/class/module boundary."""
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if p is None:
            return False
        if isinstance(p, (ast.With, ast.AsyncWith)):
            return True
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            return False
        cur = p
    return False


def attr_call_parts(node: ast.AST):
    """For a Call like ``a.b()`` return ``("a", "b")``; for ``a.b.c()`` return
    ``("a.b", "c")``. Returns ``(None, None)`` for non attribute-calls."""
    if not isinstance(node, ast.Call):
        return None, None
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None, None
    attr = func.attr
    value = func.value
    if isinstance(value, ast.Name):
        return value.id, attr
    if isinstance(value, ast.Attribute):
        # best-effort dotted prefix, e.g. urllib.request.urlopen
        parts = []
        cur = value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts)), attr
    return None, attr


# --- Inline suppression (# noqa) --------------------------------------------------

_NOQA_RE = re.compile(r"#\s*noqa\b(?::\s*(?P<codes>[A-Za-z0-9_, ]+))?", re.IGNORECASE)


def _parse_noqa_lines(source: str) -> dict[int, set[str] | None]:
    """Map 1-indexed line number -> suppressed codes, or ``None`` for a bare
    ``# noqa`` that suppresses every finding on that line.

    Same convention flake8/ruff use: a trailing ``# noqa`` (optionally
    ``# noqa: CH001,CH002``) on the offending physical line. This is a
    text-level scan, not an AST one - a real ``# noqa`` inside a string
    literal would false-suppress, but that's the same trade-off every
    other tool using this convention already makes, and matching their
    exact syntax means a codebase can suppress codehound and flake8/ruff
    findings side by side on the same line.
    """
    suppressed: dict[int, set[str] | None] = {}
    for lineno, line in enumerate(source.splitlines(), start=1):
        match = _NOQA_RE.search(line)
        if match is None:
            continue
        codes_text = match.group("codes")
        if codes_text is None:
            suppressed[lineno] = None
        else:
            codes = {c.strip().upper() for c in re.split(r"[,\s]+", codes_text) if c.strip()}
            suppressed[lineno] = codes
    return suppressed


def _is_suppressed(finding: Finding, noqa_lines: dict[int, set[str] | None]) -> bool:
    if finding.line not in noqa_lines:
        return False
    codes = noqa_lines[finding.line]
    return codes is None or finding.code.upper() in codes


# --- File discovery and orchestration ---------------------------------------------


def iter_python_files(root: str, skip_dirs: frozenset = DEFAULT_SKIP_DIRS) -> Iterator[str]:
    if os.path.isfile(root):
        if root.endswith(".py"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if fname.endswith(".py"):
                yield os.path.join(dirpath, fname)


def scan_file(path: str, checks: list[Check]) -> list[Finding]:
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    parents = build_parents(tree)
    findings: list[Finding] = []
    for check in checks:
        findings.extend(check.run(tree, parents, path))
    noqa_lines = _parse_noqa_lines(source)
    if noqa_lines:
        findings = [f for f in findings if not _is_suppressed(f, noqa_lines)]
    return findings


def _scan_file_worker(args: tuple[str, list[Check]]) -> list[Finding]:
    path, checks = args
    return scan_file(path, checks)


def scan_files(
    paths: list[str],
    checks: list[Check],
    workers: int | None = None,
) -> list[Finding]:
    """Scan an already-expanded list of file paths (no directory walking),
    in parallel across a process pool once there are enough files to make
    that worthwhile - one call, one pool, regardless of how many separate
    root paths a CLI invocation was given.
    """
    if not paths:
        return []
    if workers is None:
        workers = os.cpu_count() or 1

    findings: list[Finding] = []
    if workers <= 1 or len(paths) < _MIN_FILES_FOR_PARALLEL:
        for path in paths:
            findings.extend(scan_file(path, checks))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            for result in executor.map(_scan_file_worker, [(p, checks) for p in paths]):
                findings.extend(result)
    findings.sort(key=lambda f: (f.path, f.line, f.col, f.code))
    return findings


def scan_path(
    root: str,
    checks: list[Check],
    skip_dirs: frozenset = DEFAULT_SKIP_DIRS,
    workers: int | None = None,
) -> list[Finding]:
    return scan_files(list(iter_python_files(root, skip_dirs)), checks, workers=workers)
