# Architecture

This document explains how `codehound` is built, the design decisions behind it,
and how to extend it. It is meant to be readable end-to-end in ten minutes.

## The one-sentence summary

`codehound` walks a Python file's Abstract Syntax Tree (AST), runs a set of small
independent **checks** against every node, and reports **findings** — each a
precise `path:line:col: CODE message` pointing at a likely correctness or
async-safety bug.

## Why an AST and not regex / grep

A regex for "blocking call in an async function" cannot answer the two questions
that decide whether the pattern is actually a bug:

1. *Is the enclosing function `async`?* — requires knowing the function that
   syntactically contains the call.
2. *Is the call awaited?* — `await client.post(...)` is fine; `client.post(...)`
   is not. These differ by one AST node, not by any text near the call.

The AST gives structure: an `await` is an `ast.Await` node wrapping a `Call`; an
async function is an `ast.AsyncFunctionDef`. Checks ask structural questions, so
they are precise where grep is noisy. The cost is that comments and formatting
are invisible to the AST — which is exactly why `codehound` is a bug finder, not
a style linter.

## Module layout

```
src/codehound/
├── core.py          # engine: discovery, parsing, the Finding/Check contract,
│                    #   parent map, and shared AST predicates
├── cli.py           # `scan` / `list`, text|json|csv output, exit codes
├── checks/
│   ├── __init__.py  # the check registry (ALL_CHECKS) + get_checks() selector
│   ├── blocking_async.py     CH001
│   ├── mutable_defaults.py   CH002
│   ├── datetime_utcnow.py    CH003
│   ├── get_event_loop.py     CH004
│   ├── resource_leak.py      CH005
│   └── floating_task.py      CH006
└── __init__.py      # public API surface + __version__
```

~750 lines of source, zero runtime dependencies (standard-library `ast` only).

## The core contract

Two dataclasses/classes define everything:

```python
@dataclass(frozen=True)
class Finding:
    path: str; line: int; col: int; code: str; message: str

class Check:
    code: str; name: str; description: str
    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]: ...
```

A check receives three things: the parsed `tree`, a precomputed `parents` map,
and the file `path`. It returns a list of `Finding`s. That's the whole interface
— which is why adding a rule is one file plus one registry line plus a test.

## The parent map — the one non-obvious piece

Python's `ast` nodes know their children but **not their parent**. Several
questions ("what function contains this call?", "is this call awaited?", "is this
`open()` inside a `with`?") require walking *upward*. So `core.build_parents`
does a single pass and records `id(child) -> parent`:

```python
def build_parents(tree):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents
```

Built once per file and handed to every check, so the O(n) walk isn't repeated.
Three shared predicates are built on top of it:

- `enclosing_function(node, parents)` — climb to the nearest `FunctionDef` /
  `AsyncFunctionDef`.
- `is_awaited(node, parents)` — is the node's direct parent an `ast.Await`?
- `inside_with_statement(node, parents)` — climb to a `With`/`AsyncWith`,
  stopping at the function/class/module boundary.

## How a scan runs

1. `iter_python_files(root)` walks the tree, skipping vendored / generated /
   test / example directories (`DEFAULT_SKIP_DIRS`) — those deliberately contain
   "bad" code and would drown real findings.
2. `scan_file(path, checks)` reads the file, `ast.parse`s it (a `SyntaxError`
   yields zero findings rather than crashing the run), builds the parent map
   once, and runs every check.
3. `scan_path` aggregates and sorts findings by `(path, line, col, code)` so
   output is deterministic — important for diffing in CI.

## The six checks

| Code | Detects | Key structural test |
|------|---------|--------------------|
| CH001 | blocking call (`time.sleep`, `requests.*`, `subprocess.*`…) in an `async def` | enclosing fn is `AsyncFunctionDef` **and** the call is **not** awaited |
| CH002 | mutable default argument (`def f(x=[])`) | a default node is a `List`/`Dict`/`Set` literal or a `list()/dict()/set()/…` factory call |
| CH003 | `datetime.utcnow()` / `utcfromtimestamp()` | attribute call whose receiver resolves to `datetime` |
| CH004 | `asyncio.get_event_loop()` | attribute `get_event_loop` on a `Name` `asyncio` |
| CH005 | `f = open(...)` never closed | assignment from `open()`, not inside a `with`, no matching `.close()` in the function, not `return`ed |
| CH006 | discarded `create_task()` / `ensure_future()` | a bare `Expr` statement wrapping the call (result not bound/awaited/returned) |

Each lives in its own file with a module docstring explaining the bug and a
real-world example of where it was found.

## False-positive discipline

The most important design value: **a finding must be defensible.** Several
suppressions exist specifically to avoid noise:

- **CH001** skips awaited calls. (A local variable named `requests` that is
  actually an async client — seen for real in AutoGPT — was a false positive
  until this guard was added.)
- **CH005** does not flag a handle that is `return`ed (the caller owns closing
  it) or explicitly `.close()`d anywhere in the function.
- **CH006** does not flag `TaskGroup.create_task(...)` — the group holds the
  reference — only `asyncio`/loop receivers whose result is discarded.

The test suite asserts **both directions** for every rule: the bad pattern *is*
flagged, and the idiomatic fix is *not*.

## CLI and CI integration

`codehound scan <path>` prints `path:line:col: CODE message`, supports
`--select CH001,CH006`, `--format json|csv`, and `--include-tests`. It exits
**non-zero when findings exist** (unless `--exit-zero`), so it drops into CI as a
gate: `run: codehound scan src`. `codehound list` prints the rule catalog from
the registry — the single source of truth.

## Extending it

To add a rule:

1. Create `checks/my_rule.py` with a `Check` subclass and a `run` method.
2. Add it to `ALL_CHECKS` in `checks/__init__.py`.
3. Add paired tests (flagged / not-flagged) to `tests/test_checks.py`.

No other wiring — the CLI, selection, and output handle it automatically.

## Testing

`tests/test_checks.py` parses small inline snippets and asserts finding counts.
Tests run on Python 3.9 / 3.11 / 3.12 in GitHub Actions, plus a self-scan
(`codehound scan src`) so the tool is held to its own standard.
