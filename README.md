<p align="center">
  <img src="assets/logo.png" alt="codehound" width="220">
</p>

<h1 align="center">codehound</h1>

**An AST-based static analyzer that hunts *real* bugs in large Python codebases — seven of the ten rules are backed by a bug that was actually found and merged into a major open-source AI framework; the other three are hardening rules verified against real false positives instead.**

[![CI](https://github.com/kratos0718/codehound/actions/workflows/ci.yml/badge.svg)](https://github.com/kratos0718/codehound/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/codehound.svg)](https://pypi.org/project/codehound/)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21851079.svg)](https://doi.org/10.5281/zenodo.21851079)

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

## Install

```bash
pip install codehound
```

Zero dependencies — it's ~750 lines on top of the standard-library `ast` module, so this installs instantly and runs fully offline, no API key or network call involved.

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

# machine-readable output for CI dashboards
codehound scan path/to/project --format json
codehound scan path/to/project --format csv

# GitHub Code Scanning (Security tab) can ingest this directly
codehound scan path/to/project --format sarif > results.sarif

# list every available check
codehound list
```

`codehound scan` exits **non-zero when it finds issues**, so it drops straight into CI:

```yaml
- run: codehound scan src   # fails the build on a regression
```

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
    rev: v1.3.0
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
| **CH010** | `loop-closure-capture` | A `lambda` inside a `for` loop (or comprehension) that's *stored* (appended, assigned, returned) and captures the loop variable by reference — every stored instance ends up sharing the loop's **final** value. | **accelerate** (HuggingFace) — `MegatronEngine.get_module_config`'s `param_sync_func` list, PR #4273 |

`codehound list` prints this from the source of truth.

CH007-CH010 don't have found-and-merged bugs behind all of them the way
CH001-CH006 do - three are hardening rules for well-known Python
correctness gotchas rather than something this project personally
tracked down first. CH010 is the exception: it found a genuine, serious
bug on its own, in HuggingFace's `accelerate` - see below. Building all
four surfaced real false positives, each one fixed before shipping:

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

**One check we built and did not ship: CH011 `exception-chaining`**
(`except X as e: raise Y(...)` with no `from e`, discarding the real
traceback - overlaps flake8-bugbear B904). It worked exactly as designed,
but at a scale that says more about how common the pattern is than about
anything worth flagging: **1,911 hits across the same ~20-framework
corpus**. Shipping a check that fires that often would make every scan
result mostly CH011 noise, undermining the "a finding must be defensible"
standard the rest of this tool holds itself to. Built, measured, and
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
    └── loop_closure_capture.py (CH010)
```

Each check receives a parsed `ast` tree plus the precomputed parent map and returns `Finding`s. Adding a rule is one file + one registry line + a test. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full walkthrough of the engine, the parent map, and the design decisions.

**False-positive discipline is a feature.** CH005 won't flag a handle that's `return`ed (the caller owns it) or explicitly `.close()`d. CH006 won't flag `TaskGroup.create_task` (the group holds the reference). CH001 only fires when the *enclosing* function is `async`. CH007 scopes `self.foo()` matches to async methods on the *same* class as the call site, and bare `foo()` matches to module-level async functions that aren't shadowed by a same-named parameter. CH009 doesn't flag a thread handed off as *any* object's attribute, not just `self`. CH010 only fires when a lambda is directly stored (appended, assigned, returned), not merely passed as a callback argument that gets consumed on the spot. All four of those guards exist because of real false positives caught while building the checks (see above). The test suite asserts both "bad code is flagged" and "correct code is not."

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
- [ ] Cross-module resolution for CH007/CH009 (currently same-file only)
- [ ] Sync HTTP clients constructed inside async request handlers
- [ ] `--fix` for the mechanical rules (CH002, CH003, CH004)

---

## License

MIT © Abhinav Tarigoppula
