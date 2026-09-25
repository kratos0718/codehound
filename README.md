<p align="center">
  <img src="assets/logo.png" alt="codehound" width="220">
</p>

<h1 align="center">codehound</h1>

**An AST-based static analyzer that hunts *real* bugs in large Python codebases — one hundred and four checks, eight backed by a bug that was actually found and merged (or opened as a PR) into a major open-source AI framework, the rest hardening rules verified against real false positives across a ~29-framework validation corpus instead of just reasoned about.**

[![CI](https://github.com/kratos0718/codehound/actions/workflows/ci.yml/badge.svg)](https://github.com/kratos0718/codehound/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/codehound.svg)](https://pypi.org/project/codehound/)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21851079.svg)](https://doi.org/10.5281/zenodo.21851079)

**[Try it in your browser — no install](https://kratos0718.github.io/codehound/)** — paste Python, click Scan, see real findings from all 104 checks. Runs entirely client-side via [Pyodide](https://pyodide.org) (Python compiled to WebAssembly); your code never leaves the page.

Most linters flag style. `codehound` flags the *subtle correctness and async-safety bugs* that slip past code review and only bite in production — event-loop stalls, shared mutable state, leaked file descriptors, fire-and-forget tasks that get garbage-collected mid-run.

Most of the checks below aren't theoretical. **I wrote them after finding — and fixing, via a merged pull request — that exact bug in a real, popular framework** (agno 25k⭐, crewAI 30k⭐, mem0, llama_index, accelerate).

---

## See it in action

Pointing `codehound` at [agno](https://github.com/agno-agi/agno) (a 25k⭐ AI agent framework) surfaced real, previously-unreported bugs:

```console
$ codehound scan agno/libs/agno/agno --select CH001,CH006

agno/integrations/discord/client.py:90:26: CH001 `requests.get()` blocks the event loop
    inside async function `on_message`; use the async equivalent.
agno/tracing/exporter.py:112:16: CH006 `asyncio.create_task(...)` result is discarded;
    keep a reference (the loop only holds a weak ref, so the task may be GC'd mid-run).

Found 2 issue(s) (CH001: 1, CH006: 1)
```

**Both of these became merged/​open fixes upstream.** The first froze the Discord bot's event loop on every video/document attachment; the second could silently drop telemetry when its export task was garbage-collected mid-run. `codehound` found them in seconds — see [`docs/FINDINGS.md`](docs/FINDINGS.md) for the full provenance of every rule.

---

## Why this exists

I was contributing bug fixes to large AI frameworks and noticed the same handful of mistakes recurring across codebases. Instead of hunting them by hand, I encoded each one as an AST rule. `codehound` is the result: point it at a repo and it finds the bugs I'd otherwise have to read 100k lines to spot.

> It found the bugs behind these merged fixes — and is built to find the next one.

---

## How this compares

Being upfront about overlap: `codehound` is not the only tool that catches some of these patterns, and pretending otherwise wouldn't survive five minutes of someone actually checking. [Ruff](https://docs.astral.sh/ruff/)'s `RUF006` already catches a discarded `asyncio.create_task()` (CH006), `flake8-async`'s `ASYNC300` predates it. Ruff's `RUF012` already catches mutable class-level defaults (CH026), `F632` catches `is`-literal comparisons (CH025), `B006`/`UP005`/`E722` cover mutable-default-arguments/deprecated-unittest-aliases/bare-except (CH002/CH024/CH020). Pylint's `W1518` (`method-cache-max-size-none`) is close to a name-for-name match for CH011's `lru_cache`-on-instance-method leak. flake8-bugbear's `B012` also overlaps with CH029 (`return`/`break`/`continue` in `finally:`), though CH029 is narrower — bugbear also flags a bare `continue` inside a `finally:` loop body, which this project hasn't verified has the same swallowed-exception risk in every case. If you already run ruff and pylint, several of `codehound`'s checks will feel familiar.

Fourteen checks are explicit adaptations of a flake8-bugbear idea. Three are kept deliberately narrower than the source rule after checking where the broader version's false-positive risk actually lands; three others (`B016`, `B029`, `B003`) are ported close to as-is because the underlying bug has no narrower/broader version to weigh — it's a fixed fact about the language, true in every version of Python 3, with no configuration or heuristic to get wrong; `B015`/`B018` needed precision passes B018's own source doesn't have, found by actually reading corpus hits rather than guessing at scope in advance; the newest six (`B017`, `B022`, `B025`, `B035`, plus pyflakes' `F631`) are covered further down, in the "closing the gap" section on this batch.

- **CH010** extends to cover a nested `def` capturing a loop variable, the same shape bugbear's `B023` covers alongside its lambda case — the same storage-based precision guard (only fires if the function is actually stored past the iteration) applies to both.
- **CH032** takes bugbear's `B008` idea — "a call as a default argument is suspicious" — and narrows it to a curated list of ten functions (`time.time`, `datetime.now`, `random.random`, `uuid.uuid4`, …) whose result is *never* sensibly the same across calls. B008 as written also flags `def f(x=some_factory()):`, which is frequently a deliberate compute-once memoization; that ambiguity is exactly why this project didn't just port the broader rule.
- **CH033** takes `B005`'s "`.strip()` with a multi-character argument is misleading" and adds one precision pass B005 doesn't: skip the argument entirely when it contains no letter or digit. Scanning ~30 real frameworks turned up over a hundred multi-character `.strip()` calls, and the overwhelming majority — `.strip('\r\n')`, `.strip('[]')`, `.strip('\'"')`, box-drawing tree glyphs — were deliberate, correct uses of the character-*set* semantics, not the substring mistake the rule exists to catch. Only the argument that reads as a word or token (`data:`, `/v1`, `THREAD#`) is the real bug; a bag of punctuation isn't. Full before/after counts in [`docs/FINDINGS.md`](docs/FINDINGS.md).
- **CH034** (`B016`) — `raise <literal>` always raises a different, unrelated `TypeError` instead of the exception the author wrote. **CH035** (`B029`) — `except ():` can never match anything; the handler is dead code. **CH036** (`B003`) — `os.environ = {...}` rebinds the name without calling `putenv`/`unsetenv`, so the real process environment silently doesn't change. All three verified directly in a REPL before writing any AST code (`docs/FINDINGS.md` has the exact repro for each), and all three have zero false-positive risk: there's no legitimate Python where raising a literal succeeds, an empty exception tuple catches something, or reassigning `os.environ` actually syncs the environment.
- **CH037** (`B015`) — a bare comparison statement, ported as-is. **CH038** (`B018`) — a bare literal or pure-builtin-call statement, ported with two precision passes B018's actual source (inspected directly, not assumed) doesn't have: a container literal (`(a.pop(), b.pop())`, `(X, y)` probing whether both names are bound) is only flagged if every element is itself a constant, not just any `List`/`Set`/`Dict`/`Tuple`; and a call to a "pure" builtin like `set(...)` is only flagged if that name isn't shadowed elsewhere in the file (`with Progress(...) as set:` followed by `set("...")` is a real pattern in langgraph's CLI - not the builtin at all). A third pass excludes the display expression in a marimo `@app.cell`-decorated function, where the pattern is intentional, not a mistake - marimo's own smoke-test notebooks alone were over half of the very first corpus scan's hits.

**CH039 isn't a port of anything** - I couldn't find it in bugbear, pylint, Ruff, or bandit. `with threading.Lock():` constructs a lock nothing else in the process can ever reference, so it can never be contended, so it never actually synchronizes anything - not a crash, a silent no-op dressed up as mutual exclusion. Verified directly: five threads each doing `with threading.Lock():` around an 0.01s sleep finished in ~0.013s total, not the ~0.05s they'd take if the lock were actually serializing them. It's in the same family as CH009/CH012/CH028/CH031 (a floating threading/multiprocessing primitive that does nothing useful) but a different way to get there - those are about a primitive that's never *cleaned up*; this one is about a primitive that's never *shared*.

**Closing the gap toward fifty, honestly - three checks were built, corpus-scanned, and rejected outright before this batch was final.** A `.sort()`/`.reverse()`-returns-`None` check collided constantly with `np.sort()`, PyMongo cursor chaining, HuggingFace `Dataset.sort()`, and custom `.sort()` utility methods - none of which are `list.sort()`, and there's no AST-only way to tell them apart. An `Enum` duplicate-value check found the "rolling alias" idiom (`LATEST = SPECIFIC_VERSION`) in every single real hit, three for three, each one explicitly commented as intentional. An `__eq__`-without-`__hash__` check (pylint's `eq-without-hash`) found 162 hits across the corpus, and every one sampled was a hand-written value object that was never meant to be hashed in the first place - the exact same accepted tradeoff `@dataclass` makes on purpose. All three are documented, not shipped, in [`docs/FINDINGS.md`](docs/FINDINGS.md) rather than quietly dropped.

What replaced them, plus the rest of the new batch: **CH040** (`B017`) - `pytest.raises(Exception)` also catches an `AssertionError` from broken code under test. **CH041** (`B022`) - `contextlib.suppress()` with no arguments suppresses nothing, the exact same shape as CH035 one API up. **CH042** (`B025`) - the same exception type listed twice in one `try` is dead code. **CH043** - `==`/`!=` against a NaN literal always evaluates the same way; verified directly (`float('nan') == float('nan')` is `False`). **CH044** - `count += 1` in a nested function without `nonlocal` reads `count` before it's ever locally bound, crashing every time; verified directly. **CH045**/**CH046** - a duplicate dict key or set value silently collapses; found a real one in llama_index (a duplicated `"url"` key almost certainly masking a missing field) and a striking one in transformers (a Unicode whitespace-normalization set where several visually-indistinguishable characters turned out to be true duplicates). **CH048** (`F631`) - `assert (x, "message")` is always true; CPython's own compiler already warns about this, but the warning is easy to miss in real CI output. **CH049** and **CH050** both needed a real precision pass after their first corpus scan, the same discipline as CH033/CH038: CH049 (a `@staticmethod` reading `self`/`cls`) initially flagged vllm's `self = Cls.__new__(Cls)` factory idiom, litellm's plain reuse of `cls` as a local variable name, and agno's `cls` bound by a set comprehension's own `for cls in ...` - fixed by treating any local binding of the name, anywhere in the method's own scope, as proof it isn't reading something unbound. CH050 (`B035`, a dict comprehension's key never varying) initially flagged 18 real occurrences of one specific, entirely correct idiom - `{doc_hash: doc_id for doc_id, doc in items.items() if (doc_hash := doc.get("doc_hash"))}`, filtering and deriving the key in the same walrus - cut to a single, honestly ambiguous hit in AutoGPT once walrus targets bound in a generator's `if` clause counted as "varies per iteration" too.

**CH047 isn't a port either, and it's found more real bugs than any other single check in this project.** `@contextlib.contextmanager` runs everything after `yield` as its cleanup, but only if the `with`-block body doesn't raise - Python re-raises at the `yield` itself, and cleanup code with no `try:`/`finally:` around it simply doesn't run on that path. Verified directly, then found at real scale across eight different projects so far: litellm has a database transaction that's supposed to commit after `yield` and doesn't - no rollback either - if the caller's code raises; peft's environment-variable context manager sets `os.environ` values, yields, and restores them afterward, but never restores them if the wrapped code raises, leaking modified env vars for the rest of the process; agno's two FastAPI app-lifespan managers close MCP connections and an httpx client pool after `yield`, silently skipping that cleanup on any startup/shutdown error; mlflow has a metrics batch that's flushed after `yield` and isn't; SQLAlchemy has two DDL-event dispatchers (`before_create`/`after_create`, `before_drop`/`after_drop`) that skip the `after_*` event entirely if the actual CREATE/DROP statement fails; Poetry's own `secure()` config writer - named for the `0o600` permissions it's supposed to guarantee - skips writing the file at all if the caller's change raises. None have been filed yet - see [`docs/FINDINGS.md`](docs/FINDINGS.md) for the per-repo policy check and the full list, including two lower-severity test-only hits (Flask, Celery).

**Verification didn't stop at shipping - re-scanning a wider corpus after the fact found (and fixed) real precision gaps in checks that had already been trusted for a while.** CH011 (`lru-cache-on-method`, one of the checks with actual merged fixes behind it) turned out to match *any* decorator named `cache` by bare attribute name - SQLAlchemy's dialect classes use their own `@reflection.cache` on dozens of methods, a completely different, non-leaking decorator that only caches when the caller explicitly opts in. Fixed by only trusting `lru_cache`/`cache` when it can actually be `functools`'s. Separately, CH009/CH012/CH028 (threads/processes/timers) were each missing an escape shape their siblings CH016/CH027/CH031 (sockets/subprocesses/pools) already had - a handle appended to a list that's itself an object's attribute, not just assigned directly. Found via a real false positive in uvicorn's multi-worker supervisor. Both are documented in full, including exactly how many corpus hits each fix removed, in [`docs/FINDINGS.md`](docs/FINDINGS.md).

What actually seems to be missing elsewhere, as far as I've been able to find:

- **Floating threading/multiprocessing primitives.** `flake8-async`'s blocking-call rules (`ASYNC2xx`) and Ruff's `RUF006` cover `asyncio` specifically; I couldn't find any linter — Ruff, flake8-async, pylint, bandit — that flags a `threading.Thread`/`multiprocessing.Process`/`threading.Timer`/`multiprocessing.Pool` that's started but never joined, cancelled, or closed (CH009, CH012, CH028, CH031). This isn't a niche pattern; it's the exact same bug as the asyncio case, just one abstraction layer down, and nothing else checks for it.
- **Unawaited coroutines.** Calling an `async def` function as a bare statement — no `await`, no scheduling — silently drops the whole call (CH007). Ruff has an [open, unresolved issue](https://github.com/astral-sh/ruff/issues/9833) asking for exactly this; as of writing, nothing ships it.
- **Blocking calls to non-stdlib clients inside async functions.** `flake8-async`'s `ASYNC2xx` family only recognizes a fixed denylist (`requests`, `httpx`, `urllib3`, `subprocess`, `open`, `time.sleep`) — a synchronous call to a vector-DB client, an LLM SDK, or any other third-party library inside an `async def` isn't on anyone's list yet. CH001 is on that same denylist today; extending it to common AI/agent SDKs (the exact libraries the frameworks this tool is validated against actually use) is on the roadmap below.

And a difference in kind, not just coverage: every check here is checked against a real corpus, not just reasoned about. [`docs/FINDINGS.md`](docs/FINDINGS.md) has a running ledger of every false positive found while building each check (with the exact framework and line), and two checks that were built, measured, and **rejected outright** when the pattern turned out to be either too common to be a defensible finding (1,911 hits) or premised on something that was actually false (the first two real hits checked turned out to be correct code). I haven't found another static-analysis tool — commercial or open-source — that publishes this kind of "we built it, checked it against real code, and turned it down" ledger. Most tools that market themselves on "catches real bugs" (Greptile, Qodo, CodeRabbit) report an aggregate detection-rate benchmark, not per-rule provenance you can click through to an actual merged fix.

**Closing the "toy project" gaps, honestly.** Ruff is a single, fast binary with editor integrations, a plugin-free config file, autofix, and inline suppression - table stakes for a tool people actually adopt, not just admire. `codehound` isn't going to out-perform a Rust tool by staying pure Python, but it now has the parts of that list that don't require rewriting the whole thing: a `[tool.codehound]` block in `pyproject.toml`, `# noqa`/`# noqa: CH001` inline suppression (same syntax flake8/ruff already use, so it doesn't collide with either), `--fix` for the two checks where the rewrite is genuinely unambiguous (CH017 always, CH004 only inside `async def` - guessing wrong on the rest would be worse than not fixing them), and scanning parallelized across a process pool once there's enough files to make that worth it. Measured, not claimed: a full scan of HuggingFace's `transformers` (thousands of files) went from 57 seconds to 12 - verified byte-identical against the sequential result first, not just "seems faster."

---

## Install

```bash
pip install codehound
```

Zero dependencies — it's ~5,900 lines on top of the standard-library `ast` module, so this installs instantly and runs fully offline, no API key or network call involved.

<details>
<summary>From a clone instead (for development)</summary>

```bash
pip install -e .

# or run straight from source, no install needed
PYTHONPATH=src python -m codehound.cli scan path/to/project
```

</details>

## Usage

```bash
# scan a project (skips tests/, docs/, examples/, vendored code by default)
codehound scan path/to/project

# scan multiple files/directories in one invocation (what pre-commit does)
codehound scan file1.py file2.py src/

# only run specific checks
codehound scan path/to/project --select CH001,CH006

# also skip extra directories beyond the built-in defaults
codehound scan path/to/project --exclude migrations,generated

# machine-readable output for CI dashboards
codehound scan path/to/project --format json
codehound scan path/to/project --format csv

# GitHub Code Scanning (Security tab) can ingest this directly
codehound scan path/to/project --format sarif > results.sarif

# rewrite the fixable findings in place, then report what's left
codehound scan path/to/project --fix

# list every available check
codehound list
```

`codehound scan` exits **non-zero when it finds issues**, so it drops straight into CI:

```yaml
- run: codehound scan src   # fails the build on a regression
```

A finding you've reviewed and want to keep suppresses the same way flake8/ruff findings do - a trailing `# noqa` (everything on that line) or `# noqa: CH001` (just that code):

```python
time.sleep(1)  # noqa: CH001 - deliberate; this branch only runs at startup, before the loop exists
```

### Config file

Drop defaults into `[tool.codehound]` in `pyproject.toml` so you don't have to repeat flags on every invocation - explicit CLI flags always win over these:

```toml
[tool.codehound]
select = ["CH001", "CH006"]   # same as --select
exclude = ["migrations"]      # extra directories to skip, merged with the built-in defaults
paths = ["src"]                # what `codehound scan` (no path args) scans
```

Requires Python 3.11+ to load (uses the standard-library `tomllib`) - on 3.9/3.10 the config file is silently skipped and every flag still works exactly the same via the CLI, since nothing about codehound itself depends on being able to read it.

### `--fix`

Only two checks ship an autofix, and deliberately so - every other check either needs a judgment call (is this "leak" actually intentional?) or an import that may or may not already be in scope, and guessing wrong there is worse than just reporting the finding:

- **CH017** - `collections.<ABC>` → `collections.abc.<ABC>`, a pure rename, always safe.
- **CH004** - `asyncio.get_event_loop()` → `asyncio.get_running_loop()`, but *only* inside an `async def`. Outside one, `get_running_loop()` raises where `get_event_loop()` wouldn't, so those calls are left as detection-only.

### GitHub Action

```yaml
- uses: kratos0718/codehound@v1
  with:
    path: src
    # select: CH001,CH006        # optional, defaults to all checks
    # fail-on-findings: "false"  # optional, report without failing the build
    # upload-sarif: "false"      # optional, skip the Code Scanning upload
```

Uploads findings to the repo's **Security → Code Scanning** tab via SARIF, in addition to failing the step (unless `fail-on-findings: "false"`).

### pre-commit

```yaml
repos:
  - repo: https://github.com/kratos0718/codehound
    rev: v1.12.1
    hooks:
      - id: codehound
```

---

## The checks

| Code | Name | What it catches | Found in the wild |
|------|------|-----------------|-------------------|
| **CH001** | `blocking-call-in-async` | A synchronous blocking call (`time.sleep`, `requests.*`, `subprocess.*`) inside an `async def` — it freezes the **entire** event loop, stalling every other coroutine. | agno Couchbase vector store (`time.sleep` in an `async` collection-overwrite path) |
| **CH002** | `mutable-default-argument` | `def f(x=[])` — the default is created once and shared across every call, silently leaking state. (flake8-bugbear B006) | agno toolkits; mem0 proxy & embedder configs |
| **CH003** | `deprecated-datetime-utcnow` | `datetime.utcnow()` / `utcfromtimestamp()` — deprecated since 3.12, returns a naive datetime that lies about its timezone. | crewAI memory subsystem (9 sites, 4 files) |
| **CH004** | `deprecated-get-event-loop` | `asyncio.get_event_loop()` outside a running loop — deprecated since 3.10. | crewAI structured-tool / Snowflake search tool |
| **CH005** | `unclosed-file-handle` | `f = open(...)` with no `with` and no matching `.close()` — leaks descriptors until `RLIMIT_NOFILE` is exhausted. | agno `OpenAITools.transcribe_audio` |
| **CH006** | `floating-task` | `asyncio.create_task(...)` whose result is discarded — the loop keeps only a *weak* reference, so the task can be GC'd before it finishes. (Ruff RUF006) | hardening rule — the most under-caught async bug |
| **CH007** | `unawaited-coroutine-call` | `foo()` where `foo` is `async def`, called as a bare statement — no `await`, no scheduling. The coroutine object is created and dropped; the body **never runs at all**. | hardening rule — see below |
| **CH008** | `asyncio-run-in-running-loop` | `asyncio.run(...)` called from inside an `async def` — always raises `RuntimeError`, immediately, every time. | hardening rule — zero corpus hits (see below) |
| **CH009** | `floating-thread` | A non-daemon `threading.Thread` that's `.start()`ed but never `.join()`ed — the thread analog of CH006. | hardening rule — see below |
| **CH010** | `loop-closure-capture` | A `lambda` *or* nested `def` inside a `for` loop (or comprehension) that's *stored* (appended, assigned, returned) and captures the loop variable by reference — every stored instance ends up sharing the loop's **final** value. | **accelerate** (HuggingFace) — `MegatronEngine.get_module_config`'s `param_sync_func` list, PR #4273 |
| **CH011** | `lru-cache-on-method` | `@lru_cache`/`@cache` decorating an instance method — the cache holds a strong reference to `self` forever, so every instance that ever calls the method leaks for the process lifetime. | **optuna** — `_FanovaTree`'s node-lookup methods leaked every tree built for a `get_param_importances()` call; **llama_index** — `VectaraIndex._get_corpus_key` leaked the index *and* broke its own `__del__`-based HTTP session cleanup; **litellm** — `Router._cached_get_model_group_info` leaked every `Router` even after its own documented `discard()` cleanup |
| **CH012** | `floating-process` | A non-daemon `multiprocessing.Process` that's `.start()`ed but never `.join()`ed — the process analog of CH009. | hardening rule |
| **CH013** | `discarded-future` | `ThreadPoolExecutor`/`ProcessPoolExecutor.submit(...)` called as a bare statement — the returned `Future` (and any exception raised inside the submitted work) is silently discarded. | hardening rule — real hits in litellm, accelerate, langchain |
| **CH014** | `unprotected-lock-acquire` | `lock.acquire()` outside a `with`, whose matching `.release()` isn't inside a `finally:` — an exception between acquire and release deadlocks every future caller of that lock. | hardening rule — real hits in vllm, accelerate, torchtune |
| **CH015** | `async-property` | `@property`/`@cached_property` wrapping an `async def` — accessing the attribute hands back an un-awaited coroutine object, not the value. | hardening rule |
| **CH016** | `unclosed-socket` | `socket.socket(...)` stored without a context manager or matching `.close()` — the socket analog of CH005; leaks the file descriptor. | hardening rule |
| **CH017** | `collections-abc-import` | `from collections import Mapping` (or `Sequence`, `Iterable`, …) — the ABCs were removed from `collections` itself in Python 3.10; they live in `collections.abc`. | hardening rule |
| **CH018** | `removed-asyncio-task-methods` | `asyncio.Task.current_task()` / `.all_tasks()` — both removed in Python 3.9; use `asyncio.current_task()` / `asyncio.all_tasks()`. | hardening rule |
| **CH019** | `removed-getargspec` | `inspect.getargspec(...)` — removed in Python 3.11 after a decade-plus deprecation; use `inspect.signature(...)`. | hardening rule |
| **CH020** | `bare-except` | A bare `except:` (or unused `except BaseException:`) — also catches `KeyboardInterrupt`/`SystemExit`, so Ctrl-C stops working and `sys.exit()` gets silently absorbed. | hardening rule — real hits in agno, llama_index, marimo, litellm |
| **CH021** | `removed-stdlib-module` | `import distutils` (removed 3.12) or any of the 19 PEP 594 "dead battery" modules (`cgi`, `imghdr`, `telnetlib`, `nntplib`, …, removed 3.13) — `ImportError` the moment the module loads. | hardening rule — real hit in agno (already guarded, see below) |
| **CH022** | `removed-asyncio-coroutine-decorator` | `@asyncio.coroutine` — removed in Python 3.11 after a generator-based-coroutine bridge that predates `async def`; `AttributeError` the moment the decorator line runs. | hardening rule |
| **CH023** | `removed-stdlib-attribute` | A specific removed function on a module that still imports fine — `time.clock()` (3.8), `platform.linux_distribution()`/`.dist()` (3.8), `cgi.escape()` (3.8), `base64.encodestring()`/`.decodestring()` (3.9). | hardening rule — real hit in scikit-learn |
| **CH024** | `unittest-deprecated-alias` | `self.assertEquals(...)`/`self.failUnless(...)` and a dozen other legacy `unittest.TestCase` aliases — removed in Python 3.12. | hardening rule |
| **CH025** | `is-literal-comparison` | `x is 1000` / `x is not "foo"` — `is` checks identity, not equality; relies on CPython's small-int caching / string interning, neither guaranteed. (pyflakes F632) | hardening rule — real false positive fixed in litellm's own code, see below |
| **CH026** | `mutable-class-attribute` | `class C: items = []` mutated via `self.items.append(...)` without ever being reassigned per instance — every instance shares and mutates the *same* list. | **vllm**, **llama_index**, **optuna**, **transformers** — see below |
| **CH027** | `unwaited-subprocess` | `subprocess.Popen(...)` never `.wait()`ed/`.communicate()`d with, and not context-managed — risks a zombie process and a full pipe buffer deadlocking the child. | hardening rule — real hit in dspy (already handled, see below) |
| **CH028** | `floating-timer` | `threading.Timer(...)` started but never `.cancel()`ed or handed off — nothing can stop the callback from firing later, on stale context. | hardening rule — real hits in marimo, transformers |
| **CH029** | `finally-swallows-exception` | `return`/`break`/`continue` in a `finally:` block silently discards any exception from the `try:` — the caller never sees it. | hardening rule — real hits in letta |
| **CH030** | `lru-cache-on-async-function` | `@lru_cache`/`@cache` on `async def` caches the coroutine *object*, not its result — the second call with the same arguments crashes. | hardening rule |
| **CH031** | `unclosed-pool` | `multiprocessing.Pool()` never `.close()`d/`.terminate()`d — worker processes leak for the life of the parent. | hardening rule |
| **CH032** | `nondeterministic-default-argument` | A default argument computed from `time.time()`/`datetime.now()`/`random.random()`/`uuid.uuid4()` etc. — evaluated once at definition time, so every call using the default gets the *same* value forever. (inspired by flake8-bugbear B008, narrowed to a curated function list — see below) | hardening rule — real hit in litellm (`BudgetManager.create_budget`'s `created_at=time.time()` default) |
| **CH033** | `strip-multichar-argument` | `.strip()`/`.lstrip()`/`.rstrip()` called with a multi-character string that contains a letter or digit — `str.strip(chars)` removes any of those *characters*, not the substring, from each end. (inspired by flake8-bugbear B005, narrowed to skip punctuation-only character sets — see below) | hardening rule — real hit in huggingface_hub (SSE parsing: `line.lstrip("data:").rstrip("/n")`, the second almost certainly meant `"\n"`) |
| **CH034** | `raise-literal` | `raise "some error"` / `raise None` / `raise (1, 2)` — raising anything that isn't an exception instance always fails with a *different*, unrelated `TypeError` at the exact moment something has already gone wrong. (flake8-bugbear B016) | hardening rule — real hit in llama_index (an `ImportError` fallback that raises a bare string instead) |
| **CH035** | `empty-except-tuple` | `except ():` — an empty tuple matches nothing, so the handler can never run; every exception still propagates past it. (flake8-bugbear B029) | hardening rule — zero corpus hits (see below) |
| **CH036** | `environ-reassignment` | `os.environ = {...}` rebinds the name but doesn't call `putenv`/`unsetenv` — the real process environment (what child processes and C-level `getenv` see) stays unchanged. (flake8-bugbear B003) | hardening rule — real hit in HuggingFace `datasets` (a multiprocessing restore that silently doesn't reach spawned worker processes) |
| **CH037** | `pointless-comparison-statement` | A bare `x == 5` on its own line computes a boolean and discards it — almost always a typo for `=` or a missing `assert`. (flake8-bugbear B015) | hardening rule — zero corpus hits |
| **CH038** | `useless-expression-statement` | A literal or a call to a known-pure builtin (`len`, `sorted`, `isinstance`, …) used as a bare statement has no effect. (flake8-bugbear B018, narrowed twice after real corpus false positives — see below) | hardening rule — real hits in mlflow and vllm (`all(<generator that validates/runs work per item>)` discarded — `all` short-circuits on the first falsy result, silently skipping every item after it) |
| **CH039** | `lock-constructed-inline` | `with threading.Lock():` constructs a brand-new lock nothing else can ever reference — it can never be contended, so it never actually synchronizes anything. Not from bugbear/pylint/Ruff as far as this project could find — its own idea, same family as CH009/CH012/CH028/CH031. | hardening rule — zero corpus hits; verified directly (5 threads under a per-call fresh lock ran fully concurrently, not serialized) |
| **CH040** | `assert-raises-too-broad` | `pytest.raises(Exception)`/`self.assertRaises(Exception)` also catches an `AssertionError` from anything else inside the block — broken code under test can still report as a passing test. (flake8-bugbear B017) | hardening rule — real hits in AutoGPT's test suite |
| **CH041** | `suppress-empty` | `contextlib.suppress()` with no arguments suppresses nothing — every exception still propagates past it. (flake8-bugbear B022) | hardening rule — zero corpus hits |
| **CH042** | `duplicate-except-handler` | The same exception type listed twice in one `try` (across handlers or within one tuple) — the later occurrence is unreachable dead code. (flake8-bugbear B025) | hardening rule — zero corpus hits |
| **CH043** | `nan-equality-comparison` | `==`/`!=` against a NaN literal (`float('nan')`, `math.nan`) always evaluates the same way regardless of the other operand — NaN compares unequal to everything, including itself. | hardening rule — zero corpus hits |
| **CH044** | `augassign-without-nonlocal` | `count += 1` inside a nested function, without `nonlocal count` — reads `count` before it's ever locally assigned, crashing with `UnboundLocalError` on the very first call. | hardening rule — zero corpus hits; verified directly |
| **CH045** | `duplicate-dict-key` | The same key written twice in one dict literal — the earlier entry is silently overwritten, not merged. Matches by real runtime equality (`1`/`1.0`/`True` collide as one key, same as Python itself). | hardening rule — real hit in llama_index (`"url"` key duplicated, likely masking a missing field) |
| **CH046** | `duplicate-set-value` | The same value written twice in one set literal — the duplicate silently collapses away. | hardening rule — real hit in transformers (a Unicode whitespace-normalization set with several visually-indistinguishable duplicate characters) |
| **CH047** | `contextmanager-yield-unprotected` | `@contextmanager`'s cleanup code after `yield`, with no `try:`/`finally:`, doesn't run if the `with`-block body raises — the exact inverse of what a context manager is for. Not from bugbear/pylint/Ruff — this project's own idea. | hardening rule — real hits in litellm (a transaction that never commits *or* rolls back on error), peft (a leaked environment-variable override), agno (leaked MCP/httpx connections on app-lifespan errors), mlflow (metrics never flushed) |
| **CH048** | `assert-on-tuple` | `assert (x, "message")` is always true — it's a non-empty tuple, not a condition-plus-message; CPython's own compiler already emits a `SyntaxWarning` for this, easy to miss in real CI output. (pyflakes F631) | hardening rule — zero corpus hits |
| **CH049** | `staticmethod-references-self` | A `@staticmethod` body reads `self`/`cls`, which a static method never binds to anything — crashes with `NameError` on every call. | hardening rule — zero corpus hits after two real false-positive shapes were fixed (see below) |
| **CH050** | `static-dict-comprehension-key` | A dict comprehension's key never references its own loop variable (or a walrus bound in its own `if` clause) — every iteration overwrites the same key, so only the last item survives. (flake8-bugbear B035) | hardening rule — one plausible hit in AutoGPT, honestly ambiguous (see below) |
| **CH051** | `mutation-during-iteration` | A dict/list/set is mutated while a loop iterates directly over it — a dict/set raises `RuntimeError` immediately, a list silently skips elements. Not from bugbear/pylint/Ruff — this project's own idea. | hardening rule — 4 real hits (mlflow, litellm, transformers ×2) after excluding same-key updates, a mutation immediately followed by `break`, and list `.append()`/`.extend()` (see below) |
| **CH052** | `forwarded-without-unpacking` | A function's own `*args`/`**kwargs` is passed to a call that already unpacks something else with a star, but without its own matching star — silently forwarded as one extra positional value instead of being unpacked. | hardening rule — zero corpus hits after excluding `len(args)`-style lone usage (over 2,000 false positives on the first pass) and the `dict(kwargs, **more)` merge idiom (see below) |
| **CH053** | `aliased-list-multiplication` | `[mutable_literal] * n` repeats the same object reference `n` times, not `n` independent copies — the classic `grid = [[0] * cols] * rows` 2D-init trap. Only fires when the result is later indexed and mutated cell-by-cell. | hardening rule — zero corpus hits after excluding the harmless `[[metadata]] * batch_size`-then-never-mutated idiom, which was 58 of 58 initial hits in transformers alone (see below) |
| **CH054** | `slots-blocks-dict` | A class with `__slots__` (no `__dict__`) also reads `self.__dict__` directly or uses `@cached_property`, both of which need a per-instance `__dict__` — raises on first access, not at class definition. | hardening rule — one real hit in pydantic's own base `__repr_args__`, after excluding a `hasattr(self, '__dict__')`-guarded access and classes with a custom base (see below) |
| **CH055** | `duplicate-with-target` | The same `as` name is bound twice in one `with` statement — the second context manager silently overwrites the name before the first is ever used. Not from bugbear/pylint/Ruff — this project's own idea. | hardening rule — zero corpus hits |
| **CH056** | `path-absolute-literal-join` | Joining a `pathlib.Path` with a string literal that starts with `/` discards everything joined so far — `Path('/a') / '/b'` is `Path('/b')`, not `Path('/a/b')`. | hardening rule — zero corpus hits |
| **CH057** | `reused-exhausted-iterator` | A generator/`map`/`filter`/`zip` result is consumed by two separate terminal operations (`list`, `sum`, a `for` loop, ...) — the second one gets nothing, since a one-pass iterator can't be replayed. | hardening rule — zero corpus hits |
| **CH058** | `argparse-store-true-default` | `action='store_true'` paired with `default=True` (or `store_false`/`default=False`) makes the flag a permanent no-op — there is no way to pass it and get the other value. | hardening rule — 2 real hits (litellm, transformers) |
| **CH059** | `decorator-missing-return` | A `@functools.wraps`-wrapped inner function is built but never mentioned again anywhere in the outer function — not returned, not assigned, not attached to anything. | hardening rule — zero corpus hits after excluding four legitimate installation shapes: a ternary between two wrapped inners, reassignment to another name before returning, direct attribute assignment, and a sibling wrapped helper called by another wrapper (see below) |
| **CH060** | `falsy-and-or-ternary` | `(cond and a) or b` silently picks `b` when `a` is a falsy literal, even when `cond` is true — the pre-ternary `and`/`or` idiom, broken exactly the way real conditional expressions exist to fix. | hardening rule — zero corpus hits |
| **CH061** | `regex-backspace-escape` | A regex pattern string contains a literal backspace byte — almost always `\b` written without an `r''` prefix, so Python turned it into a backspace character before the regex engine ever saw it, silently breaking the word-boundary match. Not from bugbear/pylint/Ruff, and not caught by flake8's own invalid-escape warning either, since `\b` **is** a valid Python escape. | hardening rule — zero corpus hits |
| **CH062** | `total-ordering-missing-eq` | A class decorated with `@functools.total_ordering` defines no `__eq__` of its own — it silently falls back to identity-based equality, so two instances with equal data compare unequal, and every comparison method derived from that inherits the wrong answer. | hardening rule — zero corpus hits |
| **CH063** | `unbounded-cycle-consumption` | `itertools.cycle(...)` passed directly to `list`/`sum`/`sorted`/etc. — `cycle` is infinite by definition, so anything that tries to consume it in full hangs forever instead of raising. | hardening rule — zero corpus hits |
| **CH064** | `asyncio-wait-bare-coroutine` | A bare coroutine call inside `asyncio.wait([...])` instead of a Task — deprecated since 3.8, a hard `TypeError` on 3.11+; verified directly against Python 3.13. | hardening rule — zero corpus hits |
| **CH065** | `dict-fromkeys-mutable-default` | `dict.fromkeys(keys, mutable_value)` assigns the *same* object to every key, not a copy per key — the same root cause as a mutable default argument (CH002), one call away. | hardening rule — zero corpus hits |
| **CH066** | `os-path-join-absolute-literal` | `os.path.join(base, '/literal', ...)` restarts from the absolute-looking literal, discarding `base` and everything before it — the `os.path` sibling of CH056's `pathlib.Path` version. | hardening rule — zero corpus hits |
| **CH067** | `namedtuple-mutable-default` | A `typing.NamedTuple` field with a mutable literal default is shared by every instance that doesn't override it — `NamedTuple` defaults work like an ordinary function's, unlike a `pydantic.BaseModel` field default, which this project's own findings log documents as correctly copied per instance. | hardening rule — real hit in optuna |
| **CH068** | `logging-extra-reserved-key` | A logging call's `extra={}` dict uses a key that's already a `LogRecord` attribute (`name`, `message`, `module`, ...) — raises `KeyError` the moment that specific call actually fires, which is easy to leave unexercised if the logger's level normally filters it out. | hardening rule — real hit in litellm |
| **CH069** | `contextvar-mutable-default` | A `contextvars.ContextVar`'s mutable default is mutated directly on `.get()` elsewhere in the file — every context that never calls `.set(...)` first shares that same object, defeating the point of a context variable. Only fires with proof of an actual in-place mutation; the first corpus scan's real hits (letta, llama_index, qdrant-client, pydantic-ai) all turned out to already use the correct copy-then-`.set()` pattern (see below). | hardening rule — zero corpus hits after narrowing |
| **CH070** | `threading-local-mutable-class-attr` | A `threading.local` subclass's class-level mutable attribute is looked up on the class itself, the same for every thread — silently defeating the one thing `threading.local` exists to guarantee. | hardening rule — zero corpus hits |
| **CH071** | `weakref-to-ephemeral-object` | `weakref.ref()`/`.proxy()` targets an object constructed inline as its own argument — nothing else holds a reference, so it can be collected before the weakref is ever used, and calling it back returns `None` silently forever. | hardening rule — zero corpus hits |
| **CH072** | `itertools-tee-original-reused` | The original iterator passed to `itertools.tee()` is iterated again afterward, silently desyncing every tee'd copy and dropping elements from all of them. | hardening rule — zero corpus hits |
| **CH073** | `str-on-bytes` | `str()` on a bytes literal or `.encode()` result produces the `b'...'` repr, not decoded text — the classic Python 2→3 porting bug. | hardening rule — zero corpus hits |
| **CH074** | `empty-literal-sequence-crash` | `random.choice`, `max`/`min` without `default=`, `functools.reduce` without an initial value, or `statistics.mean`/`median`/etc. called on a literal empty sequence — always raises, no code path where the constant becomes non-empty. | hardening rule — zero corpus hits |
| **CH075** | `repr-calls-str-recursion` | `__repr__` calls `str(self)` (or formats `self` directly) with no `__str__` defined and no base class — `object`'s default `__str__` falls back to `__repr__`, so this recurses infinitely on every call. | hardening rule — zero corpus hits |
| **CH076** | `duplicate-method-definition` | The same method name is defined twice, directly, in one class body — the second silently replaces the first, leaving the earlier one as dead code. | hardening rule — real hit in mlflow (`_Trace.get_artifact_root` defined twice) |
| **CH077** | `abstractmethod-without-abc` | `@abstractmethod` on a class with no base classes and no `metaclass=ABCMeta` does nothing — there's no enforcement mechanism, so subclasses that never implement it instantiate without error. | hardening rule — real hits across 17 projects (AutoGPT, mlflow, letta, vllm, and others) |
| **CH078** | `frozen-dataclass-post-init-mutation` | `self.x = ...` inside `__post_init__` of a `@dataclass(frozen=True)` class raises `FrozenInstanceError` — frozen blocks assignment even from its own `__post_init__`. | hardening rule — zero corpus hits |
| **CH079** | `dataclass-non-default-after-default` | A `@dataclass` field with no default is declared after one that has a default — raises `TypeError` at import time. | hardening rule — zero corpus hits after excluding `field(init=False)`, `ClassVar` fields, the `KW_ONLY` sentinel, and class-level `kw_only=True`/`init=False` (see below) |
| **CH080** | `namedtuple-non-default-after-default` | A `typing.NamedTuple` field with no default is declared after one that has a default — raises `TypeError` at import time, the `NamedTuple` sibling of CH079. | hardening rule — zero corpus hits |
| **CH081** | `slots-conflicts-class-variable` | A name in `__slots__` also has a class-level value assignment — raises `ValueError` at import time. | hardening rule — zero corpus hits after excluding classes with a custom `metaclass=` |
| **CH082** | `python2-removed-dunder` | A Python 2 special method (`__nonzero__`, `__unicode__`, `__cmp__`, `__div__`, `__getslice__`, ...) is defined — Python 3 never looks it up, silently dead code that raises no warning. | hardening rule — zero corpus hits |
| **CH083** | `json-dumps-datetime` | `json.dumps()`/`.dump()` is given a `datetime`/`date` object built inline, with no `default=`/`cls=` to handle it — raises `TypeError`. | hardening rule — zero corpus hits |
| **CH084** | `defaultdict-read-creates-key` | A `defaultdict` subscript used directly as an `if`/`while` condition's test silently inserts the key as a side effect of the read. | hardening rule — real hit in optuna |
| **CH085** | `decorator-missing-functools-wraps` | A decorator's inner wrapper calls the wrapped function (forwarding its own args/kwargs through) but has no `@functools.wraps` or equivalent — the decorated function silently loses its own `__name__`/`__doc__`/`__module__`. | hardening rule — real hits across 17 projects (AutoGPT, vllm, and others) |
| **CH086** | `deepcopy-self-with-lock` | `copy.deepcopy(self)` inside a class that constructs a `threading.Lock`/`RLock`/`Condition`/etc. as an instance attribute — always raises `TypeError`, locks can't be pickled or deep-copied. | hardening rule — zero corpus hits |
| **CH087** | `enumerate-start-offset-reindex` | `enumerate(seq, start=N)`'s offset counter is used to re-index the same `seq` — the counter is offset, but `seq` is still walked 0-indexed, so this reads the wrong element and eventually raises `IndexError`. | hardening rule — zero corpus hits |
| **CH088** | `regex-flags-passed-as-count` | A `re.X` flag (`re.IGNORECASE`, ...) passed positionally to `re.sub`/`re.subn`/`re.split` lands in the `count`/`maxsplit` slot instead of `flags` — silently ignored, replacement/splitting just stops early instead. | hardening rule — zero corpus hits |
| **CH089** | `bytes-str-join-mismatch` | `str.join()` given a list of bytes, or `bytes.join()` given a list of strings — `join()` never mixes the two families, always raises `TypeError`. | hardening rule — zero corpus hits |
| **CH090** | `exit-returns-true-unconditionally` | `__exit__`/`__aexit__` always returns `True` with no branch on the exception type — silently suppresses every exception the `with` block ever raises, not just ones it's meant to handle. | hardening rule — zero corpus hits |
| **CH091** | `hash-eq-field-mismatch` | `__hash__` uses a field `__eq__` doesn't compare — two instances `__eq__` considers equal can hash differently, breaking set/dict lookups for them. | hardening rule — real hit in semantic-kernel |
| **CH092** | `path-write-type-mismatch` | `Path.write_text()` given bytes, or `Path.write_bytes()` given a string — neither encodes/decodes implicitly, always raises `TypeError`. | hardening rule — zero corpus hits |
| **CH093** | `asyncio-to-thread-async-function` | `asyncio.to_thread()` given an async function — it only constructs a coroutine object in the worker thread, never runs its body, and the result is a never-awaited coroutine. | hardening rule — zero corpus hits |
| **CH094** | `duplicate-kwarg-via-dict-unpack` | A call passes the same keyword both explicitly and through a `**`-unpacked dict literal — both target the same parameter, raising `TypeError`. | hardening rule — zero corpus hits |
| **CH095** | `multiprocessing-spawn-lambda-target` | A `spawn`/`forkserver` multiprocessing context given a lambda as `target=`/`initializer=` — spawn pickles the target to hand it to the new interpreter, and a lambda can never be pickled. | hardening rule — zero corpus hits |
| **CH096** | `post-init-on-non-dataclass` | `__post_init__` defined on a class with no decorator, no base, and no `@dataclass`-decorated subclass inheriting it — nothing ever calls it, silently dead code. | hardening rule — zero corpus hits |
| **CH097** | `raise-not-implemented-singleton` | `raise NotImplemented` raises the singleton value, not an exception — always raises `TypeError` instead of the intended `NotImplementedError`. | hardening rule — zero corpus hits |
| **CH098** | `multiple-slots-layout-conflict` | A class inherits from two or more bases that each declare a non-empty `__slots__` — CPython can only graft one instance layout per class, raises `TypeError` at import time. | hardening rule — zero corpus hits |
| **CH099** | `maketrans-mismatched-length` | `str.maketrans(a, b)` with two literal strings of different lengths — the two-argument form pairs them up by index, always raises `ValueError`. | hardening rule — zero corpus hits |
| **CH100** | `iter-returns-self-no-next` | `__iter__` returns `self`, but the class defines no `__next__` — `iter()` succeeds, but the first `next()` call raises `TypeError`. | hardening rule — zero corpus hits |
| **CH101** | `setter-before-property` | `@x.setter`/`@x.deleter` where `x` was never bound as a property earlier in the same class — inheriting one from a base doesn't help either — always raises `NameError`. | hardening rule — zero corpus hits |
| **CH102** | `total-ordering-no-methods` | `@functools.total_ordering` with none of `__lt__`/`__le__`/`__gt__`/`__ge__` defined — `__eq__` alone isn't enough — always raises `ValueError` at class-decoration time. | hardening rule — zero corpus hits |
| **CH103** | `slots-non-identifier-string` | `__slots__` assigned a bare string that isn't itself one valid identifier (e.g. `'foo bar'`, mimicking `namedtuple`'s field-string convention) — Python treats a string as one slot name, not a delimited list — always raises `TypeError`. | hardening rule — zero corpus hits |
| **CH104** | `dataclass-field-mutable-default` | `dataclasses.field(default=[])`/`{}`/`set()` given directly instead of `default_factory` — always raises `ValueError` the moment the dataclass is defined. | hardening rule — zero corpus hits |

`codehound list` prints this from the source of truth.

CH007-CH031 don't have found-and-merged bugs behind all of them the way
CH001-CH006 do - most are hardening rules for well-known Python
correctness gotchas rather than something this project personally
tracked down first. CH010 and CH011 are the exceptions: both found
genuine bugs on their own, in HuggingFace's `accelerate`, optuna, and
llama_index - see below. Building CH007-CH010 surfaced real false
positives, each one fixed before shipping:

- **CH007** (agno): a bare `self.foo()` call matched against an unrelated
  same-named `async def foo` on a *different* class (agno's own
  sync/async "twin method" convention, e.g. `ZepTools`/`ZepAsyncTools`),
  and a plain callable parameter shadowed by an unrelated same-named
  async function hundreds of lines away in the same file.
- **CH009** (llama_index): a thread handed off through a *different*
  object's attribute, not `self` - `chat_response.write_response_to_history_thread
  = thread`, with `chat_response` itself returned and the thread joined
  later once the caller finishes consuming the stream.
- **CH010** (marimo): `sorted(rows, key=lambda row: row[sort_arg.by])`
  inside `for sort_arg in ...` - the lambda references the loop variable,
  but `sorted()` calls it *immediately*, synchronously, before the next
  iteration moves `sort_arg` on. Nothing outlives the iteration. This
  reshaped the check entirely: it now only fires when a lambda is
  directly *stored* (`.append(...)`, assignment, `return`), not merely
  passed as a callback argument to something that consumes it on the spot.

**The `accelerate` find (CH010):** `MegatronEngine.get_module_config`
builds one callback per model chunk for distributed-training parameter
sync: `[lambda x: self.optimizer.finish_param_sync(model_index, x) for
model_index in range(len(self.module))]`. Every lambda captures
`model_index` by reference; by the time any of them actually runs, the
comprehension has finished and `model_index` holds its final value for
*all* of them - whichever chunk's callback fires, it reports the
*last* chunk's index. Fixed with the standard default-argument capture
(`model_index=model_index`) and a regression test that fails on the
pre-fix code (all three callbacks report index 2) and passes on the fix.
PR: [huggingface/accelerate#4273](https://github.com/huggingface/accelerate/pull/4273).

Scanning ~20 major Python AI/ML frameworks with the fixed CH007/CH008/CH009
turned up zero further real instances beyond the ones above - itself a
result, not a null: CH008's bug fails immediately and unconditionally, so
it's very unlikely to survive basic testing; CH007 and CH009 both only
match same-file names by design, and most real cases of either are
plausibly cross-module.

**The optuna, llama_index, and litellm finds (CH011):** all three are
`@lru_cache(maxsize=None)` (or a fixed `maxsize`) decorating an instance
method - a strong reference to `self` retained for the life of the
process. In optuna, `_FanovaTree`'s node-lookup methods leak every tree
built for a `get_param_importances()` call (one per random-forest
estimator). In llama_index, `VectaraIndex._get_corpus_key` leaks the
index itself - and since `VectaraIndex.__del__` exists specifically to
close the index's `requests.Session` on garbage collection, the leak
silently disables that cleanup too, so an HTTP session leaks along with
every index. In litellm, `Router._cached_get_model_group_info` leaks
every `Router` that's ever served a request through it - proved this
survives even a correctly-called `router.discard()` (Router's own
documented cleanup method), so it isn't a "you forgot to clean up" bug.
All three fixed the same way: move the cache from a class-level decorator
to a per-instance one built in `__init__`, so it's freed with the
instance instead of outliving it - the exact pattern litellm's own
`cached_deployment_model_info` sibling method already used, just not yet
applied to this one. Each has a regression test verified to fail pre-fix
and pass post-fix.
PRs: [optuna/optuna#6859](https://github.com/optuna/optuna/pull/6859),
[run-llama/llama_index#23089](https://github.com/run-llama/llama_index/pull/23089),
[BerriAI/litellm#41582](https://github.com/BerriAI/litellm/pull/41582).

**A third CH011 shape needed a guard instead of a PR:** dspy's `Image` (a
pydantic model) caches `format()` the same way, but `Image` is frozen
(`model_config = ConfigDict(frozen=True)`), which makes it hashable and
equal *by field value*, not identity. Checked directly rather than
assumed: two separately constructed instances with equal fields hash
equal, and the second one's call is served from the first's cache entry
without ever being inserted itself — bounded, value-based memoization,
not a leak. CH011 now recognizes a frozen `@dataclass` or a frozen
pydantic model and skips it.

**CH016 found and fixed its own false positive the day it shipped.** The
first real-corpus scan of `unclosed-socket` turned up three hits in
vllm's distributed process-group rendezvous code - all three sockets were
actually handed off correctly (returned inside a tuple, collected into a
list that's itself returned, passed as an argument into a function that
takes ownership), just not in a shape CH005 (the check this one was
modeled on) ever needed to recognize, since files aren't handed off this
way nearly as often as rendezvous sockets are. Fixed by treating a name
as escaped when it's returned as part of a tuple/list or passed as an
argument to any call. A full corpus rescan afterward found zero remaining
CH016 hits.

**CH021 did the same thing twice, minutes apart.** The first real-corpus
scan found a false positive in vllm - `from .chunk import
chunk_gated_delta_rule`, a relative import of vllm's own local `chunk.py`
sibling module, not the removed stdlib `chunk`. `ast.ImportFrom.module`
is `"chunk"` either way; only `node.level` (the leading-dot count) tells
a relative import apart from an absolute one, and the check wasn't
checking it. Fixed, rescanned, and found a *second* false positive in
agno: `try: import imghdr except ImportError: import filetype` - a
real, deliberate fallback that already anticipates this exact removal,
not a bug waiting to happen. Added a second guard: skip an import inside
a `try:` body whose `except` catches `ImportError` (or anything
broader). A full corpus rescan after both fixes found zero remaining
CH021 hits.

**CH026 found four real, previously-unreported bugs on its first real
scan.** All four are the exact same shape: a class-level mutable default
(`items = []`) mutated in place via `self.items.append(...)` (or
subscript assignment) with no per-instance reassignment anywhere, so
every instance of the class shares and corrupts the *same* object. In
vllm's `AXK1ForCausalLM`, `self.packed_modules_mapping["qkv_proj"] =
[...]` patches a routing table shared by every instance of the model
class. In llama_index's `ZapierToolSpec`, `self.spec_functions.append(...)`
means a second tool-spec instance (a different API key, a different
user) inherits every action name the first instance ever registered. In
optuna's CLI `_Studies` command, `self._study_list_header.append(...)`
does the same to a table-header list. In HuggingFace transformers'
`CodeGenTokenizer`, `self.model_input_names.append("token_type_ids")`
means constructing one tokenizer with `return_token_type_ids=True`
silently changes what field every *other* `CodeGenTokenizer` instance in
the same process expects, regardless of how it was configured - exactly
the "spooky action at a distance" class of bug this project exists to
catch. None have PRs yet: vllm and transformers both require AI-assisted
PRs to carry an explicit disclosure, which this project's own policy
doesn't do, so those two are documented here rather than filed.

**CH028 hit the exact same name-collision problem CH018/CH022 already
had a guard for, because that guard didn't get reused.** The very first
corpus scan came back with ~30 hits, almost all in agno - which doesn't
use `threading.Timer` at all. `from agno.utils.timer import Timer` is
agno's own unrelated stopwatch class, called as `Timer()` with zero
arguments (real `threading.Timer` requires `interval` and `function` and
would raise `TypeError` immediately). Fixed by requiring `from threading
import Timer` before trusting a bare `Timer(...)` call - the same guard
already built for CH022's `coroutine` minutes earlier in the same
session, just not applied here the first time. Also missed CH009's
`daemon=True` escape entirely (found in weaviate-python-client's
watchdog timer, `_timeout_timer.daemon = True`, a deliberate
"outlive the caller" choice) - added both a constructor-kwarg and a
post-construction-assignment check for it, matching CH009 exactly. Real
hits remain in marimo (a non-daemon browser-opening timer, never
cancelled) and transformers (a chained, never-captured checkpoint-retry
timer).

**CH025 and CH027 each found one real bug in the first scan, and one
real gap in the check.** CH025 (is-literal-comparison) flagged litellm's
`if "usage" in response_obj is not None:` - but for the wrong reason.
`ast.Compare` puts every operand and every op from a chained comparison
in one node; checking "is there a literal anywhere" and "is there an
`is`/`is not` anywhere" independently, without pairing each op with its
own adjacent operands, matched the string literal (paired with `in`)
against the wrong op (`is not`, actually comparing `response_obj` to the
allowed singleton `None`). Fixed by walking the chain as adjacent
`(left, op, right)` triples. CH027 (unwaited-subprocess) flagged dspy's
`process = subprocess.Popen(...)`, followed by `lm.process = process` -
a real hand-off to a different object, reaped later through a separate
`terminate_process(lm.process)` call, the same "stored as any object's
attribute" escape CH009/CH016/CH028 already needed. Added it.

**CH029 found a real bug in letta on day one, and its own precision gap
right after.** The first corpus scan flagged `except Exception as e:
result["error"] = str(e)` followed by `finally: return result` in
letta's job-callback dispatcher - but that except deliberately never
re-raises (the code comment says so directly: "callback failures should
not affect job completion"), so nothing is actually pending to swallow
by the time `finally` runs. Fixed by skipping a `try` whose `except`
clauses never re-raise anywhere in their own scope - there's nothing
live left to discard at that point. The same scan also turned up a
*more serious*, still-real instance in two of letta's LLM streaming
adapters: `except BaseException: <log, then re-raise a typed error>`
immediately followed by `finally: if not stream_started: return` -
except `stream_started` is unconditionally set `True` a few lines
earlier with no other assignment anywhere in the function, so today
that specific `return` is dead code, not a currently-live swallow. Read
carefully rather than assumed, and not filed as a bug report since it
isn't actually firing right now - but flagged as exactly the kind of
fragile code a future refactor could silently turn into a real one.

**Two checks we built and did not ship.** `exception-chaining` (`except X
as e: raise Y(...)` with no `from e`, discarding the real traceback -
overlaps flake8-bugbear B904) worked exactly as designed, but at a scale
that says more about how common the pattern is than about anything worth
flagging: **1,911 hits across the same ~20-framework corpus**. Shipping a
check that fires that often would make every scan result mostly noise,
undermining the "a finding must be defensible" standard the rest of this
tool holds itself to.

`cancelled-error-swallowed` (`except asyncio.CancelledError: pass` -
premise: silently swallowing task cancellation is a bug) went further
than volume alone: the **first two real hits checked**, in two different
frameworks, were both correct code, not bugs. agno's was `existing_task.
cancel(); try: await existing_task; except CancelledError: pass` - the
textbook-correct way to await a task's own cancellation. letta's was an
explicit, logged recovery path (`except (CancelledError, ...) as e: logger
.info(...); <continue processing>`) with a comment literally saying it was
overriding the cancellation on purpose. Unlike the exception-chaining
volume problem, this one meant the check's core premise was false in a
large fraction of real occurrences - so it was deleted outright rather
than kept at a lower confidence tier. Both are: built, measured, and
deliberately left out - a real decision, not an oversight.

---

## How it works

```
codehound/
├── core.py          # file discovery, AST parsing, the Finding/Check contract,
│                    #   and a child→parent map so checks can ask "what's my
│                    #   enclosing function / am I inside a `with`?"
├── cli.py           # `scan` / `list`, text|json|csv|sarif output, CI-friendly exit codes
├── sarif.py         # SARIF 2.1.0 output for GitHub Code Scanning
├── terminal.py      # colored text output (auto-disabled for non-TTY / NO_COLOR)
└── checks/          # one small, independently-tested class per rule
    ├── blocking_async.py     (CH001)
    ├── mutable_defaults.py   (CH002)
    ├── datetime_utcnow.py    (CH003)
    ├── get_event_loop.py     (CH004)
    ├── resource_leak.py      (CH005)
    ├── floating_task.py      (CH006)
    ├── unawaited_coroutine.py (CH007)
    ├── asyncio_run_in_loop.py (CH008)
    ├── floating_thread.py     (CH009)
    ├── loop_closure_capture.py (CH010)
    ├── lru_cache_on_method.py  (CH011)
    ├── floating_process.py     (CH012)
    ├── discarded_future.py     (CH013)
    ├── unprotected_lock.py     (CH014)
    ├── async_property.py       (CH015)
    ├── unclosed_socket.py      (CH016)
    ├── collections_abc_import.py (CH017)
    ├── removed_asyncio_task_methods.py (CH018)
    ├── removed_getargspec.py   (CH019)
    ├── bare_except.py          (CH020)
    ├── removed_stdlib_module.py (CH021)
    ├── asyncio_coroutine_decorator.py (CH022)
    ├── removed_stdlib_attribute.py (CH023)
    ├── unittest_deprecated_alias.py (CH024)
    ├── is_literal_comparison.py (CH025)
    ├── mutable_class_attribute.py (CH026)
    ├── unwaited_subprocess.py  (CH027)
    ├── floating_timer.py       (CH028)
    ├── finally_swallows_exception.py (CH029)
    ├── lru_cache_on_async_function.py (CH030)
    └── unclosed_pool.py        (CH031)
```

Each check receives a parsed `ast` tree plus the precomputed parent map and returns `Finding`s. Adding a rule is one file + one registry line + a test. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full walkthrough of the engine, the parent map, and the design decisions.

**False-positive discipline is a feature.** CH005 won't flag a handle that's `return`ed (the caller owns it) or explicitly `.close()`d. CH006 won't flag `TaskGroup.create_task` (the group holds the reference). CH001 only fires when the *enclosing* function is `async`. CH007 scopes `self.foo()` matches to async methods on the *same* class as the call site, and bare `foo()` matches to module-level async functions that aren't shadowed by a same-named parameter. CH009 doesn't flag a thread handed off as *any* object's attribute, not just `self`. CH010 only fires when a lambda is directly stored (appended, assigned, returned), not merely passed as a callback argument that gets consumed on the spot. CH016 doesn't flag a socket returned as part of a tuple/list, or passed as an argument to any call (as opposed to being the receiver of a call on itself) — real patterns found in vllm's rendezvous code. CH020 won't flag a `BaseException` handler whose bound name is actually referenced, or whose body re-raises anywhere in its own scope (not counting a nested try/except's own handler) — both real patterns found in agno. CH021 doesn't flag a relative import (`node.level != 0`) of a same-named local module, or an import already inside a `try:`/`except ImportError:` fallback — real patterns found in vllm and agno respectively. CH025 pairs each chained comparison's op with only its own adjacent operands, rather than matching a literal and an `is`/`is not` anywhere in the same chain independently — a real pattern found in litellm. CH027 and CH028 both recognize a handle stored as *any* object's attribute as a hand-off, matching CH009/CH016's precedent — real patterns found in dspy and weaviate-python-client respectively. CH028 also only trusts a bare `Timer(...)` when `from threading import Timer` was actually seen — real hits in agno were its own unrelated stopwatch class. CH029 skips a `try` whose `except` clauses never re-raise anywhere in their own scope — a real pattern in letta where the exception is deliberately logged and recorded, never propagated, so a `return` in `finally` isn't discarding anything live. CH033 skips a `.strip()` argument that's every character the same (`.strip('```')`) or made entirely of punctuation/whitespace with no letter or digit (`.strip('\r\n')`, `.strip('[]')`) — real patterns found across nearly every framework scanned, all deliberate uses of the character-*set* semantics rather than the substring mistake the check exists to catch. All of those guards exist because of real false positives caught while building the checks (see above and [`docs/FINDINGS.md`](docs/FINDINGS.md)). The test suite asserts both "bad code is flagged" and "correct code is not."

---

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Every check has paired tests: the buggy pattern *is* flagged, and the idiomatic fix is *not*.

---

## Roadmap

- [x] `await` on a non-awaited coroutine (missing-await detection) — CH007
- [x] PyPI release — `pip install codehound`
- [x] `asyncio.run()` inside a running loop — CH008
- [x] Non-daemon thread started without a join — CH009 (the thread analog of CH006)
- [x] Loop-variable closure capture in lambdas — CH010
- [x] Pre-commit hook — `.pre-commit-hooks.yaml`
- [x] GitHub Action — `action.yml`, uploads SARIF to Code Scanning
- [x] SARIF output — `--format sarif`
- [x] Colored terminal output (auto-disabled for non-TTY / `NO_COLOR`)
- [x] Multi-path `scan` invocation (what the pre-commit hook needs)
- [x] 20 checks — memory leaks (`lru_cache` on methods), floating processes,
      discarded futures, unprotected locks, async properties, unclosed
      sockets, removed-in-3.9/3.10/3.11 stdlib APIs, bare `except:` — CH011-CH020
- [x] 22 checks — removed stdlib modules (`distutils`, PEP 594 "dead
      batteries"), removed `@asyncio.coroutine` decorator — CH021-CH022
- [x] 28 checks — removed stdlib functions, deprecated unittest aliases,
      `is`-literal comparisons, mutable class attributes, unwaited
      subprocesses, floating timers — CH023-CH028
- [x] 31 checks — `finally:` blocks that swallow exceptions, `lru_cache`
      on async functions, unclosed `multiprocessing.Pool` — CH029-CH031
- [x] Inline `# noqa` / `# noqa: CH001` suppression
- [x] `[tool.codehound]` project config in `pyproject.toml` (`select`,
      `exclude`, `paths` — Python 3.11+ to load, every flag still works
      without it on 3.9/3.10)
- [x] `--fix` — CH017 always, CH004 only inside `async def` (CH002/CH003
      turned out to need judgment calls or import-injection this tool
      won't guess at, so they stay detection-only; see docs/ARCHITECTURE.md)
- [x] Parallelize scanning across files for large codebases — a full
      HuggingFace transformers scan went from 57s to 12s (measured,
      byte-identical output verified against the sequential run)
- [x] 33 checks — nested-`def` loop-closure capture alongside lambdas
      (CH010, same shape as bugbear's B023), nondeterministic default
      arguments, multi-character `.strip()` arguments — CH032-CH033
- [x] 36 checks — raising a literal instead of an exception, an empty
      `except ()` tuple that can never match, direct `os.environ`
      reassignment that doesn't sync the real environment — CH034-CH036
- [x] 39 checks — a bare comparison/literal/pure-call statement that
      discards its result, a lock constructed inline that can never
      be shared — CH037-CH039
- [x] 50 checks — too-broad `pytest.raises`, an empty `contextlib.suppress()`,
      duplicate except handlers/dict keys/set values, NaN equality,
      a missing `nonlocal`, unprotected `@contextmanager` cleanup, an
      always-true tupled `assert`, a `@staticmethod` reading `self`,
      a dict comprehension key that never varies — CH040-CH050
- [x] 60 checks — mutating a dict/list/set while iterating over it,
      forwarding `*args`/`**kwargs` without the unpacking star, the
      `[[0] * cols] * rows` aliasing trap, `__slots__` classes that still
      reach for `self.__dict__`, a duplicate `with ... as` target, a
      `Path` join a literal secretly resets to absolute, replaying an
      exhausted generator, an argparse flag `default`d to its own
      effect, a decorator that builds its wrapper and never hands it
      back, and the broken pre-ternary `and`/`or` idiom — CH051-CH060
- [x] 70 checks — a regex pattern with a literal backspace byte instead of
      a raw `\b`, `@total_ordering` missing the `__eq__` it needs to
      derive correct comparisons, piping an infinite `itertools.cycle`
      into something that tries to consume it in full, a bare coroutine
      inside `asyncio.wait([...])`, `dict.fromkeys` aliasing one value
      across every key, `os.path.join`'s absolute-literal reset, a
      `NamedTuple` field with a mutable default, a logging `extra={}`
      key that collides with a `LogRecord` attribute, a `ContextVar`
      mutated in place on `.get()`, and a `threading.local` subclass
      leaking a class-level mutable attribute across every thread —
      CH061-CH070
- [x] 88 checks — `@abstractmethod` with no `ABCMeta` to enforce it (real
      hits across 17 projects), a decorator's wrapper missing
      `@functools.wraps` (real hits across 17 more), dataclass/NamedTuple
      field ordering, `__slots__` conflicting with a class variable,
      Python 2 dunders (`__nonzero__`, `__unicode__`) that Python 3
      silently never calls, a `defaultdict` subscript read inside an
      `if` inserting the key as a side effect, `json.dumps()` on a raw
      `datetime`, a weakref to an object with no other reference,
      `itertools.tee`'s original iterator reused, and a regex flag
      landing in `re.sub`'s `count` slot instead of `flags` — CH071-CH088
- [x] 100 checks — `__hash__` using a field `__eq__` doesn't compare
      (real hit in semantic-kernel), `__exit__` unconditionally
      suppressing every exception, `str`/`bytes` mixed into the same
      `.join()`, `Path.write_text()`/`write_bytes()` given the wrong
      type, `asyncio.to_thread()` given an async function (only
      constructs the coroutine, never runs it), the same keyword passed
      both directly and through a `**`-unpacked dict, a lambda target on
      a spawn/forkserver multiprocessing context, `__post_init__` on a
      class nothing calls it on, `raise NotImplemented` instead of
      `NotImplementedError`, two `__slots__`-declaring bases colliding,
      `str.maketrans()` with mismatched-length arguments, and `__iter__`
      returning `self` with no `__next__` — CH089-CH100
- [x] 104 checks — a `@x.setter`/`@x.deleter` where `x` was never bound
      as a property earlier in the class (inheriting one from a base
      doesn't help either), `@total_ordering` with none of the four
      ordering dunders defined, `__slots__` given a non-identifier
      string (Python treats it as one slot name, not a delimited list),
      and `dataclasses.field(default=[])` instead of `default_factory`
      — CH101-CH104. Also fixed a real precision gap in CH081 (slots
      conflicting with a class variable): it only checked plain
      assignments, missing the identical conflict a same-named method
      or `@property` raises.
- [x] Fixed a false positive in CH005 (unclosed file handle): it only
      recognized `name.close()` called directly, missing the deferred
      idiom `closer = name.close` extracted now and invoked as
      `closer()` later — the exact pattern in CPython's vendored
      `lib2to3.pgen2.ParserGenerator.__init__`, found while scanning
      `black`'s copy of it.
- [x] Fixed two false positives in CH091 (hash/eq field mismatch), both
      found scanning `redis-py`: an `__eq__` that's an `@abstractmethod`
      stub (`AbstractRetry`) carries no information about what a real
      subclass override will compare, so it's skipped now instead of
      being treated as "compares zero fields"; an `__eq__` defined as
      `return hash(self) == hash(other)` (`CacheEntry`) is
      self-consistent by construction — there's no separate field list
      for it to fall out of sync with — and is recognized as such rather
      than flagged for "comparing nothing."
- [x] Fixed a false positive in CH090 (`__exit__` unconditionally
      returns `True`): flask's `_CollectErrors.__exit__` does exactly
      that, but only after appending the exception to `self.errors` for
      a separate `raise_any()` call to re-raise as a group later — a
      deliberate collect-and-defer pattern, not a silent swallow. Now
      skipped when the exception value is captured into an attribute or
      appended to a container anywhere in the method.
- [x] Fixed a false positive in CH081 (slots conflicting with a class
      variable): `'__dict__'` and `'__weakref__'` in `__slots__` don't
      create normal slot descriptors - they just re-enable an instance
      dict / weakref support - so a same-named class attribute or
      property never conflicts. Found via celery's `Proxy`, which defines
      a `__dict__` property alongside `'__dict__'` in its `__slots__`.
- [x] Fixed a false positive in CH007 (unawaited coroutine): a decorator
      can replace what calling an `async def` returns - textual's `@work`
      turns an async method into a sync call that schedules a Worker -
      so an async def is now only treated as a plain coroutine function
      when every decorator on it is known not to change that
      (`staticmethod`, `classmethod`, `abstractmethod`, `override`,
      `final`, `wraps`).
- [x] Narrowed CH052 (forwarded without unpacking): the starred
      companion argument now has to be the enclosing function's *own*
      other variadic (the real `func(*args, kwargs)` wrapper typo), not an
      unrelated starred local - celery's `apply_async((id, body), kwargs,
      **routing_options)` passes `kwargs` positionally on purpose.
      Documented a known limitation alongside it: `super().__init__(args,
      **kwargs)` feeding click's `param_decls` is syntactically identical
      to the typo and still flags; only the callee's signature can tell.
- [x] Fixed a false positive in CH014 (unprotected lock acquire): a
      release inside `except BaseException:`/bare `except:` that re-raises
      covers every failure path the way `finally:` would, and is the only
      correct spelling when the success path deliberately hands the held
      lock to the caller for a later release - urllib3's HTTP/2 probe cache
      (`acquire_and_get` / `set_and_release`) does exactly this.
- [ ] Cross-module resolution for CH007/CH009 (currently same-file only)
- [ ] Extend CH001 to a curated denylist of sync AI/agent SDK client calls inside async functions (vector-DB clients, LLM SDKs) — the gap flake8-async's stdlib-only denylist leaves open

---

## License

MIT © Abhinav Tarigoppula
