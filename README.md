# 🐕 codehound

**An AST-based static analyzer that hunts *real* bugs in large Python codebases — every rule is backed by a bug that was actually found and merged into a major open-source AI framework.**

[![CI](https://github.com/kratos0718/codehound/actions/workflows/ci.yml/badge.svg)](https://github.com/kratos0718/codehound/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

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
# from a clone (modern pip)
pip install -e .

# or run straight from source, no install needed
PYTHONPATH=src python -m codehound.cli scan path/to/project
```

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

`codehound list` prints this from the source of truth.

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
    └── floating_task.py      (CH006)
```

Each check receives a parsed `ast` tree plus the precomputed parent map and returns `Finding`s. Adding a rule is one file + one registry line + a test. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full walkthrough of the engine, the parent map, and the design decisions.

**False-positive discipline is a feature.** CH005 won't flag a handle that's `return`ed (the caller owns it) or explicitly `.close()`d. CH006 won't flag `TaskGroup.create_task` (the group holds the reference). CH001 only fires when the *enclosing* function is `async`. The test suite asserts both "bad code is flagged" and "correct code is not."

---

## Tests

```bash
pip install -e ".[dev]"
pytest -q
```

Every check has paired tests: the buggy pattern *is* flagged, and the idiomatic fix is *not*.

---

## Roadmap

- [ ] `await` on a non-awaited coroutine (missing-await detection)
- [ ] Sync HTTP clients constructed inside async request handlers
- [ ] `--fix` for the mechanical rules (CH002, CH003, CH004)
- [ ] Pre-commit hook + PyPI release

---

## License

MIT © Abhinav Tarigoppula
