# 🐕 codehound

**An AST-based static analyzer that hunts *real* bugs in large Python codebases — six of the seven rules are backed by a bug that was actually found and merged into a major open-source AI framework; the seventh is a hardening rule verified against real false positives instead.**

[![CI](https://github.com/kratos0718/codehound/actions/workflows/ci.yml/badge.svg)](https://github.com/kratos0718/codehound/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/codehound.svg)](https://pypi.org/project/codehound/)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21851079.svg)](https://doi.org/10.5281/zenodo.21851079)

Most linters flag style. `codehound` flags the *subtle correctness and async-safety bugs* that slip past code review and only bite in production — event-loop stalls, shared mutable state, leaked file descriptors, fire-and-forget tasks that get garbage-collected mid-run.

Each of the six checks below isn't theoretical. **I wrote it after finding — and fixing, via a merged pull request — that exact bug in a real, popular framework** (agno 25k⭐, crewAI 30k⭐, mem0, huggingface_hub).

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

# only run specific checks
codehound scan path/to/project --select CH001,CH006

# machine-readable output for CI dashboards
codehound scan path/to/project --format json
codehound scan path/to/project --format csv

# list every available check
codehound list
```

`codehound scan` exits **non-zero when it finds issues**, so it drops straight into CI:

```yaml
- run: codehound scan src   # fails the build on a regression
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

`codehound list` prints this from the source of truth.

CH007 doesn't have a found-and-merged bug behind it like the other six -
it targets a well-known Python correctness gotcha (the
`RuntimeWarning: coroutine 'foo' was never awaited` you get when a
coroutine is created and discarded) rather than one this project
personally tracked down. What it does have is two real false positives
caught and fixed while building it, both against agno: a bare `self.foo()`
call matched against an unrelated same-named `async def foo` on a
*different* class (agno's own sync/async "twin method" convention, e.g.
`ZepTools`/`ZepAsyncTools`), and a plain callable parameter shadowed by an
unrelated same-named async function hundreds of lines away in the same
file. Scanning ~20 major Python AI/ML frameworks after fixing both turned
up zero real instances - itself a result, not a null: it suggests either
that mature async test suites catch this before merge, or that most real
cases are cross-module calls, which this check deliberately doesn't chase
(same-file name matching only, consistent with every other rule here).

---

## How it works

```
codehound/
├── core.py          # file discovery, AST parsing, the Finding/Check contract,
│                    #   and a child→parent map so checks can ask "what's my
│                    #   enclosing function / am I inside a `with`?"
├── cli.py           # `scan` / `list`, text|json|csv output, CI-friendly exit codes
└── checks/          # one small, independently-tested class per rule
    ├── blocking_async.py     (CH001)
    ├── mutable_defaults.py   (CH002)
    ├── datetime_utcnow.py    (CH003)
    ├── get_event_loop.py     (CH004)
    ├── resource_leak.py      (CH005)
    ├── floating_task.py      (CH006)
    └── unawaited_coroutine.py (CH007)
```

Each check receives a parsed `ast` tree plus the precomputed parent map and returns `Finding`s. Adding a rule is one file + one registry line + a test. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full walkthrough of the engine, the parent map, and the design decisions.

**False-positive discipline is a feature.** CH005 won't flag a handle that's `return`ed (the caller owns it) or explicitly `.close()`d. CH006 won't flag `TaskGroup.create_task` (the group holds the reference). CH001 only fires when the *enclosing* function is `async`. CH007 scopes `self.foo()` matches to async methods on the *same* class as the call site, and bare `foo()` matches to module-level async functions that aren't shadowed by a same-named parameter - both guards exist because of real false positives caught while building it (see above). The test suite asserts both "bad code is flagged" and "correct code is not."

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
- [ ] Cross-module resolution for CH007 (currently same-file only)
- [ ] Sync HTTP clients constructed inside async request handlers
- [ ] `--fix` for the mechanical rules (CH002, CH003, CH004)
- [ ] Pre-commit hook

---

## License

MIT © Abhinav Tarigoppula
