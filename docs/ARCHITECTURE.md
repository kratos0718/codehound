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
│                    #   parent map, shared AST predicates, noqa suppression,
│                    #   sequential + parallel scan orchestration
├── cli.py           # `scan` / `list`, text|json|csv|sarif output, exit codes
├── config.py        # [tool.codehound] in pyproject.toml (select/exclude/paths)
├── fixes.py          # --fix: CH017 always, CH004 only inside async def
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
│   ├── bare_except.py          CH020
│   ├── removed_stdlib_module.py CH021
│   ├── asyncio_coroutine_decorator.py CH022
│   ├── removed_stdlib_attribute.py CH023
│   ├── unittest_deprecated_alias.py CH024
│   ├── is_literal_comparison.py CH025
│   ├── mutable_class_attribute.py CH026
│   ├── unwaited_subprocess.py  CH027
│   ├── floating_timer.py       CH028
│   ├── finally_swallows_exception.py CH029
│   ├── lru_cache_on_async_function.py CH030
│   ├── unclosed_pool.py        CH031
│   ├── nondeterministic_default.py CH032
│   ├── strip_multichar.py      CH033
│   ├── raise_literal.py        CH034
│   ├── empty_except_tuple.py   CH035
│   ├── environ_reassignment.py CH036
│   ├── pointless_comparison.py CH037
│   ├── useless_expression.py   CH038
│   ├── lock_constructed_inline.py CH039
│   ├── assert_raises_too_broad.py CH040
│   ├── suppress_empty.py       CH041
│   ├── duplicate_except_handler.py CH042
│   ├── nan_equality.py         CH043
│   ├── augassign_without_nonlocal.py CH044
│   ├── duplicate_dict_key.py   CH045
│   ├── duplicate_set_value.py  CH046
│   ├── contextmanager_yield_unprotected.py CH047
│   ├── assert_on_tuple.py      CH048
│   ├── staticmethod_references_self.py CH049
│   ├── static_dict_comprehension_key.py CH050
│   ├── mutation_during_iteration.py CH051
│   ├── forwarded_without_unpacking.py CH052
│   ├── aliased_list_multiplication.py CH053
│   ├── slots_blocks_dict.py    CH054
│   ├── duplicate_with_target.py CH055
│   ├── path_absolute_literal_join.py CH056
│   ├── reused_exhausted_iterator.py CH057
│   ├── argparse_store_true_default.py CH058
│   ├── decorator_missing_return.py CH059
│   ├── falsy_and_or_ternary.py CH060
│   ├── regex_backspace_escape.py CH061
│   ├── total_ordering_missing_eq.py CH062
│   ├── unbounded_cycle_consumption.py CH063
│   ├── asyncio_wait_bare_coroutine.py CH064
│   ├── dict_fromkeys_mutable_default.py CH065
│   ├── os_path_join_absolute_literal.py CH066
│   ├── namedtuple_mutable_default.py CH067
│   ├── logging_extra_reserved_key.py CH068
│   ├── contextvar_mutable_default.py CH069
│   ├── threading_local_mutable_class_attr.py CH070
│   ├── weakref_to_ephemeral_object.py CH071
│   ├── itertools_tee_original_reused.py CH072
│   ├── str_on_bytes.py         CH073
│   ├── empty_literal_sequence_crash.py CH074
│   ├── repr_calls_str_recursion.py CH075
│   ├── duplicate_method_definition.py CH076
│   ├── abstractmethod_without_abc.py CH077
│   ├── frozen_dataclass_post_init_mutation.py CH078
│   ├── dataclass_non_default_after_default.py CH079
│   ├── namedtuple_non_default_after_default.py CH080
│   ├── slots_conflicts_class_variable.py CH081
│   ├── python2_removed_dunder.py CH082
│   ├── json_dumps_datetime.py  CH083
│   ├── defaultdict_read_creates_key.py CH084
│   ├── decorator_missing_functools_wraps.py CH085
│   ├── deepcopy_self_with_lock.py CH086
│   ├── enumerate_start_offset_reindex.py CH087
│   └── regex_flags_passed_as_count.py CH088
└── __init__.py      # public API surface + __version__
```

~5,900 lines of source, zero runtime dependencies (standard-library `ast` only).

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

One more shared helper doesn't need the parent map at all: `literal_value(node)`
returns a hashable Python value for a `Constant` or a `Tuple` of them - the same
value Python's own runtime equality would compare (so `1`, `1.0`, and `True`
collide, exactly like they do as real dict keys), or the `UNRESOLVED` sentinel
for anything else. CH045 and CH046 both compare AST literals this way instead
of by node identity or naive `(type, value)` pairs.

## How a scan runs

1. `iter_python_files(root)` walks the tree, skipping vendored / generated /
   test / example directories (`DEFAULT_SKIP_DIRS`) — those deliberately contain
   "bad" code and would drown real findings.
2. `scan_file(path, checks)` reads the file, `ast.parse`s it (a `SyntaxError`
   yields zero findings rather than crashing the run), builds the parent map
   once, runs every check, then strips any finding whose line carries a
   matching `# noqa` (see below).
3. `scan_files(paths, checks)` runs `scan_file` across an already-expanded
   file list, in parallel once there are enough of them (see below), then
   sorts by `(path, line, col, code)` so output is deterministic - important
   for diffing in CI. `scan_path(root, checks)` is `scan_files` plus the
   `iter_python_files` walk, kept as a convenience for a single root.
4. The CLI expands every root path argument through `iter_python_files`
   itself and calls `scan_files` exactly once for the whole invocation -
   not once per root - so a pre-commit call with many individual file
   arguments doesn't spin up a separate process pool per file.

## Inline suppression (`# noqa`)

`core._parse_noqa_lines(source)` does one text-level pass over the file's
physical lines with a regex (`#\s*noqa\b(?::\s*(?P<codes>...))?`,
case-insensitive) and returns `{line_number: codes_or_None}`. `scan_file`
filters its findings against that map after running every check -
deliberately a text scan, not an AST one, so it can't distinguish a real
`# noqa` from one that happens to sit inside a string literal, but that's
the exact same trade-off flake8 and Ruff already make with this
convention, and matching their syntax means a project can suppress
codehound and flake8/Ruff findings on the same line without either tool
choking on the other's comment.

## Project config (`[tool.codehound]`)

`config.load_config()` reads `pyproject.toml` from the current directory
via the standard-library `tomllib` (Python 3.11+) and returns a
`CodehoundConfig` with `select`/`exclude`/`paths`, defaulting every field
to empty when the file, the table, or `tomllib` itself doesn't exist -
never raises, so a missing or unparsable config is silently equivalent to
not having one. `tomllib` was deliberately not backfilled with an
optional-dependency fallback for 3.9/3.10: the CLI's own flags cover
every one of these fields identically on any supported Python version, so
skipping config-file loading there costs a convenience, never a
capability. `cli._cmd_scan` merges config values in only where the
matching CLI flag wasn't passed - explicit flags always win.

## `--fix`

`fixes.py` deliberately covers exactly two checks - CH017 (`collections.
<ABC>` → `collections.abc.<ABC>`, a pure rename, always safe) and CH004
(`asyncio.get_event_loop()` → `asyncio.get_running_loop()`, but only when
`enclosing_function` resolves to an `AsyncFunctionDef` - outside one,
`get_running_loop()` raises where `get_event_loop()` wouldn't, so that
case is left as detection-only). Every other check either needs a
judgment call this tool isn't positioned to make automatically, or an
import that may or may not already be in scope - guessing wrong there
(silently injecting an import, or leaving a `NameError`) is worse than
just reporting the finding.

Edits are computed as `(start_line, start_col, end_line, end_col,
replacement)` from the same `lineno`/`col_offset`/`end_lineno`/
`end_col_offset` fields the checks themselves already read, converted to
absolute string offsets and applied in a single pass sorted in *reverse*
start-offset order - so an earlier edit in the file is never shifted by a
later one changing the string's length ahead of it. `cli._apply_fixes`
runs this over every matched file, writes back only the ones that
actually changed, then the normal scan runs afterward against the
now-fixed source, so `--fix`'s reported remaining findings reflect
reality rather than double-counting what was just rewritten.

One documented limitation, inherited from `ast` itself rather than
introduced here: `col_offset` counts UTF-8 *bytes*, not characters, so an
edit on a line with multi-byte characters before the edit point could
land a column off. This doesn't affect the overwhelmingly common case of
ASCII source before the edit site.

## Parallel scanning

`scan_files` sequentially scans below `_MIN_FILES_FOR_PARALLEL` (16) files
- a process pool's startup cost isn't worth it for that few, and it's
also exactly the shape of a typical pre-commit invocation (a handful of
changed files as separate arguments). Above that threshold, it hands the
work to a `concurrent.futures.ProcessPoolExecutor` sized to
`os.cpu_count()` by default, mapping a module-level `_scan_file_worker`
(needs to be a plain top-level function, not a closure, to pickle across
process boundaries) over `(path, checks)` pairs - `Check` instances hold
no state beyond their class attributes, so they pickle without any
special handling. Findings are collected back and sorted once, identical
to the sequential path. Verified, not just assumed safe: a full scan of
HuggingFace's `transformers` produced byte-identical output at `workers=1`
and at the default worker count, while cutting wall-clock time from 57
seconds to 12.

## The eighty-eight checks

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
| CH010 | lambda *or* nested `def` in a loop captures the loop variable by reference | `Lambda`/`FunctionDef`/`AsyncFunctionDef` referencing a `for`-loop's target name, *directly stored* (appended/assigned/returned - for a `def`, checked via its name rather than the statement itself) rather than passed as a callback argument that's consumed immediately |
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
| CH021 | `import`/`from` of a removed stdlib module (`distutils`, PEP 594 modules) | import's top-level module name is in a curated removed-module set, `ImportFrom.level == 0` (absolute), not inside a `try:` body with an `ImportError`-or-broader handler |
| CH022 | `@asyncio.coroutine` decorator | decorator resolves to `asyncio.coroutine`, or bare `coroutine` only when `from asyncio import coroutine` was seen in the file |
| CH023 | a specific removed stdlib function (`time.clock`, `cgi.escape`, …) | `(module, attribute)` pair in a curated dict, module actually imported |
| CH024 | deprecated `unittest.TestCase` alias (`assertEquals`, …) | `self.<alias>(...)` call where `<alias>` is in a curated dict |
| CH025 | `is`/`is not` compared against a str/bytes/int/float literal | walks the comparison chain as adjacent `(left, op, right)` triples, flags only pairs where the op is `Is`/`IsNot` and one side is a non-singleton literal |
| CH026 | class-level mutable default mutated in place via `self.<attr>` | class-body `Name = List/Dict/Set` (or empty factory call), a `self.<attr>` in-place mutation exists, no `self.<attr> = ...` reassignment anywhere in the class |
| CH027 | `subprocess.Popen(...)` never waited/communicated | assignment from `Popen(...)`, not `with`-managed, no `.wait()`/`.communicate()`, not returned/passed-as-argument/stored-as-attribute |
| CH028 | `threading.Timer(...)` started, never cancelled | same shape as CH009, `.cancel()` instead of `.join()`, plus `daemon=True` escape; bare `Timer` only trusted with `from threading import Timer` |
| CH029 | `return`/`break`/`continue` in `finally:` swallows a pending exception | scoped walk of `finalbody` for an escaping `Return`, or a `Break`/`Continue` whose owning loop is outside the `finally:`; skipped entirely when every `except` handler never re-raises |
| CH030 | `@lru_cache`/`@cache` on `async def` | decorator resolves to `lru_cache`/`cache`, decorated node is an `AsyncFunctionDef` (method or module-level) |
| CH031 | `multiprocessing.Pool(...)` never closed | same shape as CH005/CH016/CH027/CH028, `.close()`/`.terminate()` instead of `.join()`/`.cancel()` |
| CH032 | default argument evaluates a nondeterministic call (`time.time()`, `random.random()`, `uuid.uuid4()`, …) | default value (positional or keyword-only) is a `Call` whose `(module, attribute)` pair is in a curated set of ten always-changes-per-call functions |
| CH033 | `.strip()`/`.lstrip()`/`.rstrip()` argument reads as a substring, not a character set | single string-literal argument, length > 1, more than one distinct character, and at least one character is alphanumeric |
| CH034 | `raise` with a literal instead of an exception instance | `Raise.exc` is a `Constant`/`JoinedStr`/`List`/`Dict`/`Set`/`Tuple` node |
| CH035 | `except ():` matches nothing | `ExceptHandler.type` is a `Tuple` with zero elements |
| CH036 | direct assignment to `os.environ` | `Assign` target is an `Attribute` node, `attr == "environ"`, receiver is a bare `Name` `os` |
| CH037 | comparison used as a bare statement | `Expr` whose `value` is a `Compare` node |
| CH038 | literal/pure-builtin-call used as a bare statement | `Expr` whose `value` is a constant-only `List`/`Set`/`Dict`/`Tuple`, a non-string `Constant`, or a call to an unshadowed curated-pure builtin; skipped if it's the display statement of an `@*.cell`-decorated function |
| CH039 | lock/RLock constructed directly in the `with`/`async with` that acquires it | `withitem.context_expr` is itself a `Call` to `threading.Lock`/`RLock`, `multiprocessing.Lock`/`RLock`, or `asyncio.Lock` |
| CH040 | `pytest.raises(Exception)`/`self.assertRaises(Exception)` too broad | `with` context expr is a `Call` to `pytest.raises`/`*.assertRaises*` whose first arg (positional or `expected_exception=`) is a bare `Exception`/`BaseException` name |
| CH041 | `contextlib.suppress()` with zero arguments | `Call` to `contextlib.suppress` (or bare `suppress` if actually imported from `contextlib`) with no args/kwargs |
| CH042 | the same exception type in more than one place in a `try` | walks each `Try`'s handlers in order, matching `Name`/tuple-of-`Name` types against a running `seen` set |
| CH043 | `==`/`!=` against `float('nan')`/`math.nan`/`np.nan` | same adjacent-triple chained-comparison walk as CH025, checking `Eq`/`NotEq` against a curated NaN-literal shape |
| CH044 | augmented assignment to an enclosing-scope name, no `nonlocal` | `AugAssign` target is a bare `Name`, its enclosing function is itself nested in another function, the name isn't a parameter or `nonlocal`/`global`-declared, and it's the *only* local binding of that name in the function (skipping further-nested scopes) |
| CH045 | duplicate key in a dict literal | two `Dict.keys` entries resolve to an equal `literal_value` |
| CH046 | duplicate value in a set literal | two `Set.elts` entries resolve to an equal `literal_value` |
| CH047 | `@contextmanager` cleanup after `yield` not wrapped in `try`/`finally` | a bare top-level `yield` (or one inside a `Try` with no `finalbody`) has another statement after it at the same block level |
| CH048 | `assert` on a non-empty tuple literal | `Assert.test` is a `Tuple` with at least one element |
| CH049 | `@staticmethod` body reads `self`/`cls` | a `Name`/`Load` reference to `self`/`cls` whose nearest enclosing function is the `@staticmethod` itself, not a parameter, and has no local `Store`-context binding anywhere in that function's own scope (skipping nested scopes) |
| CH050 | dict comprehension key never varies per iteration | `DictComp.key` has no reference to any `for`-target name or walrus target bound in a generator's `iter`/`ifs`, and contains no `Call` itself |
| CH051 | mutating the exact dict/list/set a loop iterates over | `For`/`AsyncFor` whose `iter` is a bare `Name` or a `.keys()`/`.values()`/`.items()` call on one, with a `del`/`Store`-subscript/mutating-method call on that same name in the loop body; excludes a `Store`-subscript keyed by the loop's own current key (by name or by a literal already proven equal via an enclosing `if key == 'literal':`), a mutation immediately followed by an unconditional `break` in the same block, and `.append()`/`.extend()` |
| CH052 | a function's own `*args`/`**kwargs` forwarded to a call without its star | a bare `Name` argument in a `Call` matching the enclosing function's `vararg`/`kwarg` param name, only when that same call already has another `Starred` arg or a `**`-keyword; excludes `dict(...)`/`.update(...)` calls |
| CH053 | `[mutable_literal] * n` aliasing, later mutated | RHS of a top-level `Assign` to a `Name` is a `BinOp(Mult)` where one side is a single-element `List` whose element is itself a `List`/`Dict`/`Set` (or another `[x] * n` `BinOp`), and a later statement in the same block does a nested `Subscript`-`Store` on that name (`name[i][j] = ...`) |
| CH054 | `__slots__` class relying on a per-instance `__dict__` | `ClassDef` with no base (or only `object`) and a literal `__slots__` not containing `"__dict__"`, that either reads `self.__dict__` (unless guarded by an enclosing `if hasattr(self, '__dict__'):`) or decorates a method with `@cached_property` |
| CH055 | duplicate `as` target in one `with` | two `withitem.optional_vars` in the same `With`/`AsyncWith` are `Name` nodes with the same `id` |
| CH056 | `Path(...) / '/literal'` resets to absolute | `BinOp(Div)` whose left side is (or chains back to) a `Path`/`PurePath`/`PosixPath`/`PurePosixPath` call, and whose right side is a string `Constant` starting with `/` |
| CH057 | replaying an exhausted generator/`map`/`filter`/`zip` | a `Name` bound from a `GeneratorExp`/`map`/`filter`/`zip` call is passed as the first arg to two different terminal calls (`list`/`tuple`/`set`/`sorted`/`sum`/`max`/`min`) or used as two separate `for`-loop iterables in the same function, with no reassignment in between |
| CH058 | `argparse` flag `default`d to its own effect | `add_argument(...)` call with `action='store_true'`/`default=True` or `action='store_false'`/`default=False` |
| CH059 | `@wraps`-decorated inner function never referenced again | a top-level nested `FunctionDef`/`AsyncFunctionDef` decorated with `functools.wraps(...)`/`wraps(...)` whose name doesn't appear as a `Name` anywhere else in the outer function (including inside sibling `@wraps`-decorated helpers) |
| CH060 | `(cond and a) or b` with a falsy literal `a` | `BoolOp(Or)` whose first value is a `BoolOp(And)` ending in a literal that's falsy (`literal_value` is falsy, or an empty `List`/`Dict`/`Set`/`Tuple`) |
| CH061 | regex pattern string with a literal backspace byte | first positional arg to `re.<func>(...)` (receiver must be the bare name `re`) is a `Constant` string containing `\x08` |
| CH062 | `@total_ordering` class with no `__eq__` | `ClassDef` decorated with `functools.total_ordering`/`total_ordering`, no base other than `object`, and no `__eq__` in its own body |
| CH063 | `itertools.cycle(...)` piped into a full consumer | `Call` to `list`/`tuple`/`set`/`frozenset`/`sorted`/`sum`/`max`/`min` whose first arg is itself a `Call` to `cycle`/`itertools.cycle` |
| CH064 | bare coroutine inside `asyncio.wait([...])` | `asyncio.wait(...)`'s first arg is a `List`/`Tuple`/`Set` literal containing a `Call` element not itself wrapped in `create_task`/`ensure_future` |
| CH065 | `dict.fromkeys(keys, mutable_value)` | `Call` to `dict.fromkeys` whose second positional arg is a `List`/`Dict`/`Set` literal or a no-arg `list`/`dict`/`set` call |
| CH066 | `os.path.join(base, '/literal', ...)` | `Call` to `os.path.join`/`path.join` where any argument after the first is a string `Constant` starting with `/` |
| CH067 | `NamedTuple` field with a mutable literal default | `ClassDef` with a `NamedTuple` base, containing an `AnnAssign` whose default value is a `List`/`Dict`/`Set` literal or a no-arg `list`/`dict`/`set` call |
| CH068 | logging `extra={}` key colliding with a `LogRecord` attribute | a call to a logging method's `extra=` keyword is a `Dict` literal with a string key matching a curated set of real `LogRecord.__dict__` attribute names (verified directly against the actual attribute list) |
| CH069 | `ContextVar` mutable default mutated in place | `ContextVar(..., default=mutable_literal)` assigned to a `Name`, where that same name's `.get()` result is later mutated directly (`.get().append(...)`, `.get()[k] = v`) anywhere else in the module |
| CH070 | `threading.local` subclass, class-level mutable attribute | `ClassDef` with a `threading.local` base, containing a plain `Assign` to a mutable literal at the class level |
| CH071 | `weakref.ref()`/`.proxy()` targeting an ephemeral object | `Call` to `weakref.ref`/`.proxy` whose single argument is itself a `Call` (object built inline), excluding getter-like calls (`.get`/`.pop`/`.find`/`.fetch`/`.load`/`.read`) |
| CH072 | original iterator reused after `itertools.tee()` | `Assign` from `tee(name, ...)` where `name` is a bare `Name`, and a later node in the same scope consumes that exact name (`for x in name:`, `next(name)`, or `list`/`tuple`/`sorted`/`sum`/`set`/`min`/`max` wrapping it) |
| CH073 | `str()` on bytes instead of `.decode()` | single-arg `Call` to `str` whose argument is a bytes `Constant` or a `.encode(...)` call |
| CH074 | a call guaranteed to raise on an empty sequence, given a literal empty one | `random.choice`/`max`/`min` (no `default=`)/`functools.reduce` (no initial)/`statistics.mean` family, whose sequence argument is an empty `List`/`Tuple`/`Dict` literal or a no-arg `set()` |
| CH075 | `__repr__` calling `str(self)` with no `__str__`, no base class | `ClassDef` with zero bases, a `__repr__` but no `__str__`, whose body contains `str(self)`, an f-string embedding `self`, or `"{}"​.format(self)` |
| CH076 | the same method name defined twice in one class body | `ClassDef.body` grouped by `FunctionDef`/`AsyncFunctionDef` name, 2+ entries, none decorated with `property`/`*.setter`/`*.deleter`/`*.getter`/`overload`/`*.register` |
| CH077 | `@abstractmethod` with no enforcement mechanism | `ClassDef` with zero bases and no `metaclass=` keyword, containing a method decorated with `abstractmethod`/`abstractproperty` |
| CH078 | `self.x = ...` inside `__post_init__` of a frozen dataclass | `ClassDef` decorated with `@dataclass(..., frozen=True)`, whose `__post_init__` contains a direct `Assign`/`AugAssign` to `self.<attr>` |
| CH079 | dataclass field with no default after one that has a default | `ClassDef` decorated with `@dataclass`, walking `AnnAssign` fields in order; excludes `field(kw_only=True)`, `field(init=False)`, `ClassVar[...]` annotations, the `KW_ONLY` sentinel, and class-level `kw_only=True`/`init=False` |
| CH080 | `NamedTuple` field with no default after one that has a default | `ClassDef` with a `NamedTuple` base, same ordering walk as CH079 without the dataclass-specific exemptions |
| CH081 | `__slots__` name also given a class-level value | `ClassDef` with no custom `metaclass=`, where a literal `__slots__` name also appears as an `Assign`/valued-`AnnAssign` target elsewhere in the body |
| CH082 | a Python 2 special method that Python 3 never looks up | `ClassDef` method name in a curated removed/renamed-dunder set (`__nonzero__`, `__unicode__`, `__cmp__`, `__div__`, `__getslice__`, ...) |
| CH083 | `json.dumps()`/`.dump()` given a `datetime`/`date` built inline | `Call` to `json.dumps`/`.dump` with no `default=`/`cls=` keyword, whose value argument is a `Call` to a known datetime-factory attribute (`now`/`utcnow`/`today`/`fromtimestamp`/...) on a receiver whose name contains "date"/"time" |
| CH084 | `defaultdict` subscript read directly as an `if`/`while` test | `Assign` from `defaultdict(...)` to a `Name`, where a later `If`/`While` test is (optionally `not`-wrapped) a bare `Subscript` on that exact name |
| CH085 | decorator's inner wrapper missing `@functools.wraps` | outer function's first param is called by its sole inner function (in the inner's own scope, not a further-nested one), forwarding at least one of the inner's own params unchanged; inner is directly returned by outer; excludes manual `wrapper.__name__ = ...` and `functools.update_wrapper(wrapper, ...)` |
| CH086 | `copy.deepcopy(self)` in a class holding a lock attribute | `ClassDef` whose own body sets `self.<attr> = threading.Lock()`/`RLock`/`Condition`/`Semaphore`/`Event`/`Barrier`, containing a `copy.deepcopy(self)` call in one of its methods |
| CH087 | `enumerate(seq, start=N)`'s offset counter reused to index `seq` | `For` whose `iter` is `enumerate(name, start=N)` with `N != 0`, whose body subscripts that same `name` with the loop's own index variable |
| CH088 | a `re.X` flag landing in `re.sub`/`.subn`'s `count` or `re.split`'s `maxsplit` slot | 4-arg `re.sub`/`.subn` or 3-arg `re.split` call with no `flags=` keyword, whose last positional argument is a flag-shaped `re.X` attribute or `|`-combination of them |

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
- **CH021** checks `ImportFrom.level == 0` before trusting a module name -
  a relative `from .chunk import x` has `node.module == "chunk"` too,
  indistinguishable from the real stdlib module by name alone (real,
  found in vllm's own local `chunk.py` sibling module). It also skips an
  import inside a `try:` body whose `except` catches `ImportError` or
  anything broader (real, found in agno's `try: import imghdr except
  ImportError: import filetype`) - a deliberate fallback already
  anticipates the exact removal being flagged.
- **CH025** pairs each comparison op with only its own two adjacent
  operands - a naive "is there a literal, is there an Is/IsNot, anywhere
  in the chain" check matched litellm's `"usage" in response_obj is not
  None` for the wrong reason (the literal is the left side of `in`, not
  of `is not`, which is actually comparing against the allowed
  singleton `None`).
- **CH027** and **CH028** both treat a handle stored as *any* object's
  attribute as a hand-off, matching CH009/CH016's precedent (real,
  found in dspy's `lm.process = process` and weaviate-python-client's
  watchdog timer respectively). CH028 also only trusts a bare
  `Timer(...)` when `from threading import Timer` was actually seen -
  agno's own unrelated stopwatch class, called as `Timer()` with zero
  arguments, produced ~30 false positives before this guard existed.
- **CH029** skips a `try` entirely when every `except` handler never
  re-raises anywhere in its own scope (the same nested-handler-boundary
  scoping already proven for CH020) - real, found in letta, where
  `except Exception as e: result["error"] = str(e)` deliberately never
  propagates, so a `return` in the matching `finally:` has nothing live
  to discard.

The test suite asserts **both directions** for every rule: the bad pattern *is*
flagged, and the idiomatic fix is *not*.

## CLI and CI integration

`codehound scan [<path> ...]` prints `path:line:col: CODE message`
(colored when stdout is a real terminal, plain otherwise), supports
`--select`, `--exclude`, `--format json|csv|sarif`, `--include-tests`, and
`--fix`. Paths are `nargs="*"` (not required) specifically so `[tool.
codehound]`'s `paths` can supply a default when the CLI is run bare;
`args.paths or config.paths or ["."]` is the exact fallback chain. It
still accepts multiple paths in one invocation for the same reason it
always did - that's how `pre-commit` invokes a hook (one call, every
changed file as a separate argument). It exits **non-zero when findings
exist** (unless `--exit-zero`), so it drops into CI as a gate: `run:
codehound scan src`. `codehound list` prints the rule catalog from the
registry — the single source of truth.

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
  the CLI expands and scans every root path argument in one combined
  `scan_files` call rather than one `scan_path` call per argument (avoids
  spinning up a separate process pool per file when pre-commit passes many).

## Extending it

To add a rule:

1. Create `checks/my_rule.py` with a `Check` subclass and a `run` method.
2. Add it to `ALL_CHECKS` in `checks/__init__.py`.
3. Add paired tests (flagged / not-flagged) to `tests/test_checks.py`.

No other wiring — the CLI, selection, and output handle it automatically.

A rule only gets a `--fix` entry in `fixes.py` when the rewrite is
mechanical and unambiguous with no import-injection or semantic-shift
risk (see "`--fix`" above) - most rules should stay detection-only, and
that's a feature, not a gap to close.

## Testing

`tests/test_checks.py` parses small inline snippets and asserts finding
counts, one file per check family. `tests/test_noqa.py`,
`tests/test_config.py`, `tests/test_fixes.py`, and
`tests/test_parallel_scan.py` cover the engine-level features - inline
suppression, project config, autofix, and parallel-vs-sequential
correctness - the same way, plus `tests/test_output_formats.py` for
SARIF/colored-text serialization. Tests run on Python 3.9 / 3.11 / 3.12
in GitHub Actions, plus a self-scan (`codehound scan src`) so the tool
is held to its own standard.
