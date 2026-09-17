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
├── cli.py           # `scan` / `list`, text|json|csv|sarif output, exit codes
├── sarif.py         # SARIF 2.1.0 serialization for GitHub Code Scanning
├── terminal.py      # colored text output (TTY-aware, respects NO_COLOR)
├── checks/
│   ├── __init__.py  # the check registry (ALL_CHECKS) + get_checks() selector
│   ├── blocking_async.py     CH001
│   ├── mutable_defaults.py   CH002
│   ├── datetime_utcnow.py    CH003
│   ├── get_event_loop.py     CH004
│   ├── resource_leak.py      CH005
│   ├── floating_task.py      CH006
│   ├── unawaited_coroutine.py CH007
│   ├── asyncio_run_in_loop.py CH008
│   ├── floating_thread.py     CH009
│   ├── loop_closure_capture.py CH010
│   ├── lru_cache_on_method.py  CH011
│   ├── floating_process.py     CH012
│   ├── discarded_future.py     CH013
│   ├── unprotected_lock.py     CH014
│   ├── async_property.py       CH015
│   ├── unclosed_socket.py      CH016
│   ├── collections_abc_import.py CH017
│   ├── removed_asyncio_task_methods.py CH018
│   ├── removed_getargspec.py   CH019
│   └── bare_except.py          CH020
└── __init__.py      # public API surface + __version__
```

~2,200 lines of source, zero runtime dependencies (standard-library `ast` only).

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

## The twenty checks

| Code | Detects | Key structural test |
|------|---------|--------------------|
| CH001 | blocking call (`time.sleep`, `requests.*`, `subprocess.*`…) in an `async def` | enclosing fn is `AsyncFunctionDef` **and** the call is **not** awaited |
| CH002 | mutable default argument (`def f(x=[])`) | a default node is a `List`/`Dict`/`Set` literal or a `list()/dict()/set()/…` factory call |
| CH003 | `datetime.utcnow()` / `utcfromtimestamp()` | attribute call whose receiver resolves to `datetime` |
| CH004 | `asyncio.get_event_loop()` | attribute `get_event_loop` on a `Name` `asyncio` |
| CH005 | `f = open(...)` never closed | assignment from `open()`, not inside a `with`, no matching `.close()` in the function, not `return`ed |
| CH006 | discarded `create_task()` / `ensure_future()` | a bare `Expr` statement wrapping the call (result not bound/awaited/returned) |
| CH007 | `async def` called without `await`/scheduling | bare `Expr` wrapping a `Call` whose target resolves to a same-file `async def` - module-level for bare names, same-class for `self./cls.` |
| CH008 | `asyncio.run()` called from a running loop | `Call` to `asyncio.run` whose *immediate* enclosing function is an `AsyncFunctionDef` |
| CH009 | non-daemon `threading.Thread` started, never joined | assignment/chained call to `threading.Thread(...)`, `.start()` seen, no `.join()`, no `daemon=True`, not returned/stored as any object's attribute |
| CH010 | lambda in a loop captures the loop variable by reference | `Lambda` referencing a `for`-loop's target name, *directly stored* (appended/assigned/returned) rather than passed as a callback argument that's consumed immediately |
| CH011 | `@lru_cache`/`@cache` on an instance method | decorator resolves to `lru_cache`/`cache`, enclosing scope is a `ClassDef`, not `staticmethod`/`classmethod`, class isn't a frozen dataclass/pydantic model |
| CH012 | non-daemon `multiprocessing.Process` started, never joined | same shape as CH009, for `multiprocessing.Process(...)` |
| CH013 | discarded `Executor.submit(...)` result | bare `Expr` wrapping `.submit(...)` on a name tracked back to a `ThreadPoolExecutor`/`ProcessPoolExecutor` construction |
| CH014 | `lock.acquire()` outside a `with`, `.release()` not in `finally:` | matching `.release()` call on the same name exists in the function, but no enclosing `Try.finalbody` contains it |
| CH015 | `@property`/`@cached_property` wrapping `async def` | decorated node is an `AsyncFunctionDef` |
| CH016 | `socket.socket(...)` never closed | same shape as CH005, for `socket.socket(...)`, plus escaped if returned inside a tuple/list or passed as an argument to any call |
| CH017 | `from collections import Mapping` (etc.) / `collections.Mapping` | name matches a curated ABC set, import/attribute receiver is bare `collections` (not `collections.abc`) |
| CH018 | `asyncio.Task.current_task()` / `.all_tasks()` | attribute call on `Task`, only trusted when `Task` was imported via `from asyncio import Task` |
| CH019 | `inspect.getargspec(...)` | attribute call/import resolves to `inspect.getargspec` |
| CH020 | bare `except:` / unused `except BaseException:` | handler type is `None` or `Name("BaseException")`, bound name (if any) not referenced, and no `raise` anywhere in the handler's own scope |

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
- **CH007** resolves `self.foo()`/`cls.foo()` against the async methods of
  the *same enclosing class only* — a same-named `async def foo` on a
  different class (a sync/async "twin method" pair, real in agno's
  `ZepTools`/`ZepAsyncTools`) is not a match. Bare `foo()` is checked
  against the enclosing function's own parameters first — a parameter
  shadows a same-named module-level `async def` elsewhere in the file
  (also a real false positive found while building this).
- **CH009** treats a thread assigned as *any* object's attribute as an
  intentional hand-off, not just `self.<attr>` — llama_index's chat
  engines stash the thread on a returned response object
  (`chat_response.write_response_to_history_thread = thread`), which
  joins it later once the caller finishes consuming the stream.
- **CH010** only fires when a lambda is directly *stored* (an argument to
  `.append()`/`.add()`, the value of an assignment, or `return`ed/`yield`ed)
  — not merely passed as a callback to something that calls it immediately.
  `sorted(rows, key=lambda row: row[sort_arg.by])` inside a `for sort_arg`
  loop (real, in marimo) looks identical at the AST level to the buggy
  pattern, but `sorted()` consumes the lambda synchronously within the
  same iteration, so nothing ever observes a stale value.
- **CH011** skips a frozen `@dataclass` or a pydantic model with
  `model_config = ConfigDict(frozen=True)` (or the old-style `class
  Config: frozen = True`) — a frozen class hashes and compares by field
  value, not identity, so `lru_cache` on its method memoizes by value
  (bounded by `maxsize` distinct values) instead of leaking every
  instance. Verified directly, not just reasoned about: dspy's `Image`
  caches `format()` this way, and a second, field-equal instance's call
  is served from the first instance's cache entry without ever being
  inserted itself.
- **CH016** treats a socket name as escaped if it's `return`ed as part of
  a tuple/list (not just as the bare name) or passed as an argument to
  any call, not just handed a `.close()` — vllm's rendezvous code returns
  `port, s` as a tuple, collects sockets into a list that's itself
  returned, and passes a listen socket straight into a constructor that
  takes ownership of it. Found the day the check shipped, from the first
  real-corpus scan.
- **CH020** doesn't flag a `BaseException` handler whose bound name is
  actually referenced anywhere in the body (agno's background-thread
  runner reports the caught exception back via a queue instead of
  discarding it), or a handler — bound name or not — that contains a
  `raise` anywhere in its own scope, not counting a nested try/except's
  own handler (agno's `_ensure_session` resets internal state on a failed
  connect, then bare-`raise`s to propagate the original error). Both were
  real false positives found by checking actual corpus hits, not just
  reasoning about the shape.

The test suite asserts **both directions** for every rule: the bad pattern *is*
flagged, and the idiomatic fix is *not*.

## CLI and CI integration

`codehound scan <path> [<path> ...]` prints `path:line:col: CODE message`
(colored when stdout is a real terminal, plain otherwise), supports
`--select CH001,CH006`, `--format json|csv|sarif`, and `--include-tests`. It
accepts multiple paths in one invocation - not just for convenience, but
because that's how `pre-commit` invokes a hook (one call, every changed file
as a separate argument). It exits **non-zero when findings exist** (unless
`--exit-zero`), so it drops into CI as a gate: `run: codehound scan src`.
`codehound list` prints the rule catalog from the registry — the single
source of truth.

Three integration points ship at the repo root, each a thin wrapper around
this same CLI - none of them duplicate its logic:
- `action.yml` - a composite GitHub Action. Installs codehound, runs it
  twice (once to produce `--format sarif` for the Code Scanning upload,
  once for the human-readable exit-code-bearing run), so a workflow gets
  both a Security-tab integration and a normal failing CI step from one
  `uses:` line.
- `.pre-commit-hooks.yaml` - `language: python`, `entry: codehound scan`,
  `types: [python]`. pre-commit installs codehound into its own managed
  venv and calls `codehound scan <changed files...>` - this is the reason
  `scan` takes `nargs="+"` instead of a single path.

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
