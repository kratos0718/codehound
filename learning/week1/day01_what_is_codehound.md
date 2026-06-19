# Day 01 — What is codehound & what is static analysis?

> Today is orientation. No deep code yet — you'll understand *what* the tool is, *why* it exists, and you'll *run it once*. Everything else hangs off today.

---

## 1. The problem codehound solves

When you write Python, some bugs explode immediately (a typo, a missing import). But the *dangerous* bugs are the **silent** ones — code that runs fine, passes tests, ships to production, and then misbehaves under specific conditions:

- A `time.sleep()` inside an `async` function that quietly freezes your whole server for a second.
- A `def f(x=[])` where two unrelated users end up sharing the same list.
- An `open()` with no `close()` that leaks file handles until the process crashes after a few hours.

These don't crash on line 1. They pass code review because they *look* fine. They're the bugs that page you at 3am. **codehound finds this exact category** — real, subtle, behavioral bugs — *before* they ship.

## 2. What "static analysis" means

Two ways to find bugs in code:

- **Dynamic analysis** = *run* the code and watch what happens (tests, debuggers, profilers). Problem: you only see the paths you actually execute.
- **Static analysis** = examine the code *without running it* — read its structure and reason about it. This is what linters (ruff, flake8, mypy) do, and what codehound does.

> **Static** = "at rest" (not running). **Dynamic** = "in motion" (running).

codehound never executes your code. It **reads** it, turns it into a structured tree (an AST — Day 2), and inspects that tree for the shapes of known bugs. Because it never runs anything, it's fast, safe, and works on code that doesn't even have its dependencies installed.

## 3. What codehound actually is, in one breath

> A zero-dependency Python tool that parses each `.py` file into an **AST**, then runs **six checks**, each of which walks the tree looking for one specific bug pattern, and reports every match as a **Finding** (file, line, column, code, message).

That's the whole thing. Six checks:

| Code | Name | The bug in 5 words |
|------|------|--------------------|
| CH001 | blocking-call-in-async | sync call freezes the loop |
| CH002 | mutable-default-argument | `def f(x=[])` shares state |
| CH003 | deprecated-datetime-utcnow | naive datetime lies about UTC |
| CH004 | deprecated-get-event-loop | removed-soon asyncio API |
| CH005 | unclosed-file-handle | `open()` without `close()` leaks |
| CH006 | floating-task | fire-and-forget task GC'd |

**The thing that makes codehound special:** each check isn't academic — it's distilled from a bug **you actually found and got merged** into a famous AI framework (agno, mem0, crewAI, huggingface_hub). You didn't invent rules in a vacuum; you saw a real bug, fixed it upstream, then taught your tool to find that *class* of bug everywhere.

## 4. Why "zero dependencies" matters (a real design decision)

codehound imports nothing outside Python's standard library — it uses the built-in `ast` and `os` modules and nothing else. Why is that a deliberate, defensible choice?

1. **It can't break from a dependency update.** No `pip` resolution hell, ever.
2. **It runs anywhere instantly** — `python -m codehound.cli scan .` works with a bare Python install.
3. **It's auditable** — a reviewer (or you, in an interview) can read the *entire* thing in an hour.
4. **It proves you understand the fundamentals** — you didn't `pip install` a parser; you used the language's own machinery.

> ✅ **Interview-worthy line:** *"I kept it zero-dependency on purpose — it uses only the standard-library `ast` module. That makes it trivially installable, impossible to break from upstream changes, and small enough to audit completely."*

## 5. The shape of the codebase (your map for the next 24 days)

```
src/codehound/
├── __init__.py            # the public library surface (Day 10)
├── core.py                # THE ENGINE: Finding, Check, AST helpers, file scan (Week 2)
├── cli.py                 # the `codehound scan` command (Day 21)
└── checks/
    ├── __init__.py        # the registry of all 6 checks (Day 11)
    ├── blocking_async.py   # CH001 (Day 13)
    ├── mutable_defaults.py # CH002 (Day 14)
    ├── datetime_utcnow.py  # CH003 (Day 15)
    ├── get_event_loop.py   # CH004 (Day 16)
    ├── resource_leak.py    # CH005 (Day 17)
    └── floating_task.py    # CH006 (Day 18)
tests/test_checks.py        # proves each check works AND has no false positives (Day 22)
```

Notice the **separation of concerns** — a recurring theme you'll point to in interviews:
- `core.py` knows *how to scan* but nothing about specific bugs.
- each `checks/*.py` knows *one bug* but nothing about file discovery or output.
- `cli.py` knows *how to talk to a human* but delegates all real work.

That clean split is *why* adding a new check (Day 24) takes ~40 lines and touches nothing else.

## 6. 🔧 Exercise — run it once

Open a terminal and run codehound on its own source:

```bash
cd /Users/abhinav/openSource/codehound
python -m codehound.cli list                       # see the 6 checks
python -m codehound.cli scan src                    # scan its own code (should be clean)
python -m codehound.cli scan src --format json      # same, as JSON
```

Then run it on something real and watch it find bugs:

```bash
# point it at any Python repo you have lying around
python -m codehound.cli scan /tmp/hunt/unsloth --select CH001
```

Look at the output line: `path:line:col: CODE message`. **That single line is the product.** Everything in this codebase exists to produce that line accurately. Sit with that.

## ✅ Say this out loud (Day 1 mastery check)
> *"codehound is a static analyzer — it finds bugs by reading code structure, not running it. It parses Python into an AST and runs six checks, each detecting one real bug class I'd previously found and fixed upstream in frameworks like agno and mem0. It's zero-dependency, using only the standard library, so it's tiny, fast, and auditable."*

If you can say that without looking, you've got Day 1. Tomorrow: **how Python turns your source text into the tree codehound reads.**
