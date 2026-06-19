# 🐕 codehound — 25-Day Deep Learning Path

> Goal: by Day 25 you can open `codehound`, explain **every line**, justify **every design decision**, **extend it** with a new check, and **defend it** cold in an interview with Nikhil or any recruiter. This is *your* tool — by the end it will feel like it.

**How to use this:** one folder per week, one file per day. Read the day, then open the real source file it points to side-by-side. Each day ends with a **✅ "say this out loud"** interview answer, a **💬 Interview Q&A** block, and a small **🔧 exercise**. Don't skip the exercises — typing it is how it sticks.

The whole tool is ~750 lines across 10 files. That's the point: it's small enough to understand *completely*. Most people can't explain their own projects line-by-line. After this, you can.

> **🟢 New here / forgot what "AST" means?** Start with **[codehound_from_scratch.md](codehound_from_scratch.md)** — a zero-jargon story explainer. Then use **[CODE_WALKTHROUGH_A_TO_Z.md](CODE_WALKTHROUGH_A_TO_Z.md)** as the line-by-line reference. The 25 days below go deeper, one concept at a time, each with interview questions.

---

## Week 1 — Foundations (the ground you stand on)
You can't understand a static analyzer without understanding how code becomes a tree. This week is the "why" under everything.

| Day | Title | You'll understand |
|-----|-------|-------------------|
| 01 | [What is codehound & static analysis](week1/day01_what_is_codehound.md) | What the tool does, why it exists, the big picture, run it once |
| 02 | [How Python runs your code](week1/day02_how_python_runs_code.md) | source → tokens → **AST** → bytecode; why we work at the AST level |
| 03 | [The `ast` module hands-on](week1/day03_the_ast_module.md) | Nodes, `ast.walk`, `ast.dump`, `lineno`/`col_offset`, reading a tree |
| 04 | [`Finding` & `Check` — the contract](week1/day04_finding_and_check.md) | dataclasses, the base-class pattern, the interface every check obeys |
| 05 | [The parent map](week1/day05_the_parent_map.md) | Why AST has no parents, `build_parents`, `id()`, walking upward |

## Week 2 — The engine (`core.py` + wiring, line by line)
| Day | Title | You'll understand |
|-----|-------|-------------------|
| 06 | [AST helpers I — `enclosing_function`, `is_awaited`](week2/day06_ast_helpers_i.md) | How a check asks "what function am I in? am I awaited?" |
| 07 | [AST helpers II — `inside_with_statement`, `attr_call_parts`](week2/day07_ast_helpers_ii.md) | Scope boundaries; resolving dotted names like `urllib.request.urlopen` |
| 08 | [File discovery — `iter_python_files` & the skip-dirs trick](week2/day08_file_discovery.md) | `os.walk`, the `dirnames[:] = ...` in-place prune, why we skip `tests/` |
| 09 | [Orchestration — `scan_file` & `scan_path`](week2/day09_orchestration.md) | Reading, parsing, swallowing `SyntaxError`, deterministic sorting |
| 10 | [The package — `__init__.py`, public API, `__all__`, versioning](week2/day10_the_package.md) | What "the library surface" means and why it's curated |
| 11 | [The registry — `ALL_CHECKS`, `get_checks`](week2/day11_the_registry.md) | How checks are discovered, instantiated, and filtered by `--select` |
| 12 | [Integration day — trace one finding end-to-end](week2/day12_integration_trace.md) | Run on a real repo, follow a bug from bytes to printed line |

## Week 3 — The six checks (each bug + its detector)
| Day | Title | The bug class |
|-----|-------|---------------|
| 13 | [CH001 blocking-call-in-async](week3/day13_ch001_blocking_async.md) | A sync call freezes the whole event loop |
| 14 | [CH002 mutable-default-argument](week3/day14_ch002_mutable_defaults.md) | `def f(x=[])` shares one list across all calls |
| 15 | [CH003 deprecated `datetime.utcnow()`](week3/day15_ch003_datetime_utcnow.md) | Naive datetimes that lie about being UTC |
| 16 | [CH004 deprecated `get_event_loop()`](week3/day16_ch004_get_event_loop.md) | Removed-in-future asyncio API (+ the honest false positive) |
| 17 | [CH005 unclosed-file-handle](week3/day17_ch005_resource_leak.md) | Leaked file descriptors → crash under load |
| 18 | [CH006 floating-task](week3/day18_ch006_floating_task.md) | Fire-and-forget task GC'd mid-run |
| 19 | [The shared contract & false-positive philosophy](week3/day19_contract_and_precision.md) | Why precision beats recall here |
| 20 | [The real bugs these found](week3/day20_the_real_bugs.md) | Map each check → its merged PR (agno, mem0, crewAI) |

## Week 4 — Pro level (own it & defend it)
| Day | Title | You'll be able to |
|-----|-------|-------------------|
| 21 | [The CLI — `argparse`, subcommands, formats, exit codes](week4/day21_the_cli.md) | Explain how it slots into CI |
| 22 | [Testing — `test_checks.py`, positive **and** negative cases](week4/day22_testing.md) | Explain how you prevent false positives |
| 23 | [Packaging & CI — `pyproject.toml`, `ci.yml`, zero-dependency](week4/day23_packaging_and_ci.md) | Explain how it installs and ships |
| 24 | [**Capstone:** write your own 7th check from scratch](week4/day24_capstone_seventh_check.md) | Prove you can extend it |
| 25 | [**Defend it:** the interview script + design tradeoffs](week4/day25_defend_it.md) | Walk anyone through it with confidence |

---

## The one-paragraph summary (memorize this by Day 25)
> *codehound is a zero-dependency Python static analyzer I built. It parses each file into an AST with the standard-library `ast` module, precomputes a child→parent map so checks can walk upward to ask "what function is this call in?", and runs six independent `Check` classes that each detect one real bug class — blocking calls in async, fire-and-forget tasks, mutable defaults, unclosed files, and two deprecated-API patterns. Each check is distilled from a bug I actually found and got merged into a major AI framework. It outputs text/JSON/CSV with CI-friendly exit codes.*

By Day 25, you won't be reciting that — you'll *understand* every clause of it.
