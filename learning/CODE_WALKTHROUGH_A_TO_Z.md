# codehound — A-to-Z Code Walkthrough

> Every file, every function, the important lines — explained. Goal: after reading this you can open any part of codehound and explain *what it does, how, and why* cold, to a recruiter or to Nikhil. The whole tool is ~750 lines across 10 files; small enough to know *completely*.

## 0. The 30-second big picture

codehound is a **static analyzer**: it finds bugs by reading your code *as a tree*, without running it. The pipeline for every scan is:

```
path ──> iter_python_files ──> for each .py: read text
      ──> ast.parse(text)           # source code  ->  Abstract Syntax Tree
      ──> build_parents(tree)       # precompute child->parent map
      ──> for each Check: check.run(tree, parents, path)  -> [Finding...]
      ──> sort findings, print as text / json / csv
```

The two core ideas:
1. **AST, not regex.** We turn source into a structured tree (`ast` module) so we can ask precise questions like "is this call inside an `async def`?" — impossible to do reliably with text matching.
2. **The Check contract.** Every rule is a small class with one method `run(tree, parents, path) -> list[Finding]`. Adding a new rule = adding one class. That's the whole extensibility story.

There are **6 checks**, each distilled from a *real bug I fixed* in a popular AI framework:

| Code | Name | Bug it catches | Found/fixed in |
|------|------|----------------|----------------|
| CH001 | blocking-call-in-async | sync call (`time.sleep`, `requests.get`) inside `async def` freezes the event loop | agno, unsloth |
| CH002 | mutable-default-argument | `def f(x=[])` shares one list across all calls | agno, mem0 |
| CH003 | deprecated-datetime-utcnow | `datetime.utcnow()` returns a naive datetime (deprecated 3.12) | crewAI |
| CH004 | deprecated-get-event-loop | `asyncio.get_event_loop()` deprecated outside a running loop | crewAI |
| CH005 | unclosed-file-handle | `f = open(...)` with no `with` / `.close()` leaks a descriptor | agno |
| CH006 | floating-task | `asyncio.create_task(...)` whose result is discarded can be GC'd mid-run | vLLM, autogen, OpenAI |

---

## 1. `core.py` — the engine (206 lines)

This file holds **the data model, the AST helpers, and the orchestration**. Read it top to bottom.

### 1a. `DEFAULT_SKIP_DIRS` (lines 18–44)
A `frozenset` of directory names we never descend into: VCS dirs (`.git`), caches (`__pycache__`), dependencies (`node_modules`, `site-packages`, `venv`), build output (`dist`, `build`), **and crucially `tests/`, `examples/`, `cookbook/`, `docs/`.**

> **Why skip tests/examples?** They *deliberately* contain bad patterns (a test for the mutable-default bug literally writes `def f(x=[])`). Flagging them would be noise. **Why `frozenset`?** It's immutable (safe as a shared default) and gives O(1) membership lookup.

### 1b. `Finding` dataclass (lines 47–67)
```python
@dataclass(frozen=True)
class Finding:
    path: str; line: int; col: int; code: str; message: str
```
One immutable record of a single rule violation at a source location. `frozen=True` means it can't be mutated after creation (hashable, safe to pass around). Two formatters:
- `as_text()` → `path:line:col: CODE message` — the standard compiler/linter format (clickable in editors).
- `as_dict()` → for JSON/CSV output.

> **Interview line:** "A Finding is just an immutable value object — location plus code plus message. Keeping it a dataclass means checks never deal with formatting; they emit data, and the CLI decides how to render it."

### 1c. `Check` base class (lines 70–81)
```python
class Check:
    code = ""; name = ""; description = ""
    def run(self, tree, parents, path) -> list[Finding]:
        raise NotImplementedError
```
The **contract** every rule obeys. Subclasses set three class attributes (`code` like `"CH001"`, `name`, `description`) and implement `run`. The base `run` raises `NotImplementedError` so a half-written check fails loudly.

> This is the **Strategy pattern**: each check is an interchangeable strategy with the same interface, so the engine can loop over them blindly.

### 1d. `build_parents` (lines 87–97) — the key trick
```python
def build_parents(tree):
    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents
```
**Python's AST nodes don't store their parent.** But many checks need to walk *upward* ("what function is this call in?"). So once per file we precompute a map: `id(child_node) -> parent_node`. We use `id()` (the object's memory address) as the key because AST nodes aren't hashable by value.

> **Why precompute?** Cheaper than re-searching the tree for every check. `ast.walk` visits every node; `ast.iter_child_nodes` gives the direct children. One pass builds the whole map.

### 1e. `enclosing_function` (lines 100–110)
Walks up the parent map from a node until it hits a `FunctionDef` or `AsyncFunctionDef` (or runs out → `None`). This is how CH001 asks "am I inside an `async def`?" and CH005 asks "what function owns this file handle?"

### 1f. `is_awaited` (lines 113–121)
```python
return isinstance(parents.get(id(node)), ast.Await)
```
True if the call's direct parent is an `await`. **This is a false-positive guard for CH001:** `await client.get(...)` is *non-blocking* even though `.get` looks like the sync `requests.get`. If it's awaited, we leave it alone.

### 1g. `inside_with_statement` (lines 124–137)
Walks up from a node; returns `True` if it hits a `With`/`AsyncWith` **before** hitting a function/class/module boundary. Used by CH005: a file opened inside `with open(...)` is safe, so we stop checking. The boundary check prevents us from wrongly crediting a `with` block in a *different*, outer scope.

### 1h. `attr_call_parts` (lines 140–162)
Helper that splits an attribute-call into `(receiver, method)`: `a.b()` → `("a","b")`, `urllib.request.urlopen()` → `("urllib.request","urlopen")`. Handles the nested-`Attribute` case by walking down `value` and reversing the dotted parts. (CH001 inlines its own copy of this logic.)

### 1i. `iter_python_files` (lines 168–177)
```python
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in skip_dirs]
```
Yields every `.py` file under `root`. **The magic line is `dirnames[:] = [...]`** — mutating the list *in place* tells `os.walk` to **not recurse** into skipped dirs. (Reassigning `dirnames = [...]` would NOT work — os.walk reads the same list object.) If `root` is a single file, it yields just that.

### 1j. `scan_file` (lines 180–194)
Read the file → `ast.parse` → `build_parents` → run every check, collect findings. Two `try/except` guards: file read errors (`OSError`/`UnicodeDecodeError`) and `SyntaxError` both return `[]` rather than crash the whole scan on one bad file.

### 1k. `scan_path` (lines 197–206)
Loops `iter_python_files`, accumulates findings, then **sorts deterministically** by `(path, line, col, code)`. Determinism matters: same input → same output order every run (testable, diffable).

---

## 2. `__init__.py` — the package surface (22 lines)
Re-exports the public API (`Check`, `Finding`, `scan_file`, `scan_path`, `ALL_CHECKS`, `get_checks`) and defines `__version__ = "0.1.0"`. `__all__` curates exactly what `from codehound import *` exposes.

> **Interview line:** "`__all__` is the library's contract — the surface I promise is stable. Everything else is internal."

## 3. `checks/__init__.py` — the registry (32 lines)
```python
ALL_CHECKS = [BlockingCallInAsync, MutableDefaultArgument, ... FloatingTask]

def get_checks(selected=None):
    if not selected:
        return [cls() for cls in ALL_CHECKS]          # all checks
    wanted = {s.upper() for s in selected}
    return [cls() for cls in ALL_CHECKS
            if cls.code.upper() in wanted or cls.name.upper() in wanted]
```
`ALL_CHECKS` is the list of check *classes*. `get_checks` **instantiates** them — all of them, or just the ones whose code (`CH001`) or name (`blocking-call-in-async`) matches `--select`. Case-insensitive via `.upper()`.

> This is the **registry pattern**: one list is the single source of truth for "what checks exist." Adding a check = importing it and appending here.

## 4. `cli.py` — the command line (102 lines)
- `build_parser()` (57–92): defines `codehound scan <path>` with flags `--select`, `--format {text,json,csv}`, `--include-tests`, `--exit-zero`, plus `codehound list`. Uses `argparse` subcommands; each subcommand sets `func` via `set_defaults`, so `main` just calls `args.func(args)`.
- `_cmd_scan` (14–48): parse `--select` → `get_checks` → (optionally re-include tests) → `scan_path` → render as text/json/csv. **Exit code:** returns `1` if issues found (unless `--exit-zero`), `0` if clean, `2` if no checks matched. Non-zero exit is what makes it usable in **CI** (fails the build on a finding).
- `_cmd_list` (51–54): prints each check's code/name/description.

> **Interview line:** "The CLI is a thin shell. It picks checks, calls `scan_path`, formats output, and maps results to exit codes for CI. All the logic lives in `core.py` and the checks."

---

## 5. The six checks — bug + detection logic

Every check follows the same shape: `ast.walk(tree)` over all nodes, filter to the node type it cares about, apply a few precise conditions, emit a `Finding`. Here's the *what* and the *how* for each.

### CH001 — `blocking_async.py` (BlockingCallInAsync)
**Bug:** a synchronous call like `time.sleep(30)` or `requests.get(...)` inside an `async def` blocks the **entire event loop** — every other coroutine stalls for the duration.
**Detection:**
1. Node must be a `Call` whose `func` is an `Attribute` (`module.method`).
2. Resolve the dotted module prefix (handles `urllib.request`).
3. `(module, attr)` must be in `_BLOCKING_CALLS` (a hardcoded set: `time.sleep`, all `requests.*`, `subprocess.*`, `os.system`, `urllib.request.urlopen`).
4. **Skip if `is_awaited`** (await ⇒ non-blocking) — false-positive guard.
5. `enclosing_function` must be an `AsyncFunctionDef`. (A blocking call in a *sync* function is fine — that's normal.)
→ Emits: "`module.method()` blocks the event loop inside async function `fn`; use the async equivalent."

### CH002 — `mutable_defaults.py` (MutableDefaultArgument)
**Bug:** `def f(x=[])` — the `[]` is created **once at definition time**, so all calls share the same list; mutating it leaks state between calls.
**Detection:** for each `FunctionDef`/`AsyncFunctionDef`, look at `node.args.defaults` + non-`None` `kw_defaults`. A default is mutable if it's a literal `List`/`Dict`/`Set`, **or** a `Call` to a known factory (`list`, `dict`, `set`, `Counter`, `defaultdict`, `OrderedDict`, `deque`). Flags the default's own line.

### CH003 — `datetime_utcnow.py` (DeprecatedDatetimeUtcnow)
**Bug:** `datetime.utcnow()` / `utcfromtimestamp()` return a **naive** datetime that pretends to be local time — a footgun, deprecated in 3.12.
**Detection:** `Call` whose `func.attr` ∈ {`utcnow`, `utcfromtimestamp`} **and** the receiver is `datetime` (a `Name`) or `something.datetime` (an `Attribute`). → suggest `datetime.now(timezone.utc)`.

### CH004 — `get_event_loop.py` (DeprecatedGetEventLoop)
**Bug:** `asyncio.get_event_loop()` with no running loop is deprecated since 3.10.
**Detection:** `Call` → `func.attr == "get_event_loop"` and `func.value` is the `Name` `asyncio`.
> ⚠️ **Known limitation (be honest in interviews):** *inside* a running coroutine, `get_event_loop()` is NOT deprecated. This check doesn't distinguish that context, so it can false-positive — which is exactly why maintainers rejected one of these PRs. I use that story to show I understand the difference between a lint rule and ground truth.

### CH005 — `resource_leak.py` (UnclosedFileHandle)
**Bug:** `f = open(path)` outside a `with`, never `.close()`d, leaks a file descriptor; under load you exhaust `RLIMIT_NOFILE`.
**Detection (the most sophisticated check):**
1. `Assign` whose value is a direct `open(...)` call.
2. Skip if `inside_with_statement` (a `with` manages it).
3. Collect the assigned name(s) (handles tuple/list unpacking via `_name_targets`).
4. Must be inside a function (`enclosing_function`) — function scope makes close-tracking reliable.
5. **Two escape hatches (false-positive guards):**
   - `returns_handle` — if the function `return`s the handle, the *caller* owns closing it.
   - `_has_close_call(fn, name)` — if `name.close()` appears anywhere in the function, it's handled.
6. Only if neither holds → flag "`name = open(...)` is never closed; use `with`."

### CH006 — `floating_task.py` (FloatingTask)
**Bug:** `asyncio.create_task(coro())` on its own line discards the returned task. The loop holds only a **weak reference**, so the GC can collect the task before it finishes — silently dropping the work.
**Detection:** an **`Expr` statement** (i.e. the result is *not* assigned/awaited/returned) whose value is a `Call` to `.create_task`/`.ensure_future`, where the receiver is `asyncio` **or** a name containing "loop" (catches `loop.create_task(...)`). The `Expr`-statement requirement is the crux: `task = asyncio.create_task(...)` is fine (reference kept), so we only flag the bare-statement form.

---

## 6. "Say this out loud" — the 90-second pitch

> "codehound is a ~750-line, zero-dependency static analyzer for Python. It parses each file into an AST with the standard-library `ast` module, precomputes a child-to-parent map so checks can reason about scope, then runs a set of small Check classes that each return Findings. There are six checks, and every one comes from a real bug I found and fixed in a major AI framework — blocking calls in async code, mutable default arguments, fire-and-forget asyncio tasks, file-handle leaks, and two deprecation rules. What makes it more than a toy is the false-positive handling: CH001 ignores awaited calls, CH005 won't flag a handle the function returns or closes. It runs in CI and exits non-zero on a finding. The bugs it flags are merged into unsloth and agno, and I wrote an empirical paper applying it to 29 frameworks."

## 7. FAQ / design decisions (likely questions)
- **Why AST not regex?** Regex can't tell `async def` from `def`, can't track scope, can't tell `await x.get()` from `x.get()`. AST gives structure.
- **Why zero dependencies?** Trust + portability + it forced me to actually understand `ast`. Reviewers can audit it in one sitting.
- **How do you avoid false positives?** Context guards (is_awaited, inside_with_statement, returns_handle, close-tracking) and skipping test/example dirs.
- **How would you add a check?** Write a `Check` subclass with `code/name/description` + `run`, import it in `checks/__init__.py`, append to `ALL_CHECKS`. Done.
- **Biggest limitation?** It's intraprocedural and name-based — it doesn't do type inference or cross-function flow. CH004's false positive (get_event_loop inside a running loop) is the honest example.
```
Run it:  PYTHONPATH=src python3 -m codehound.cli scan <path> --select CH001
List:    PYTHONPATH=src python3 -m codehound.cli list
```
