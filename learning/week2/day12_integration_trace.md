# Day 12 — Integration: trace one finding end-to-end

> No new code today. You connect everything from Week 2 by following a single bug from raw source text all the way to the printed line. If you can narrate this trace, you understand the engine.

---

## The input
A file `server.py`:
```python
import time

async def load_checkpoint():
    while is_training_active():
        time.sleep(0.1)          # ← the bug (this is the unsloth pattern)
```

## The trace (say each step out loud)

**1. CLI** (`cli.py`) — you run `codehound scan server.py`. `_cmd_scan` parses args, calls `get_checks(None)` → all six check instances, then `scan_path("server.py", checks)`.

**2. Discovery** (`iter_python_files`) — `server.py` is a single file ending in `.py`, so it's yielded once.

**3. `scan_file`** —
   - reads the text (UTF-8),
   - `ast.parse(source)` → an AST: `Module → AsyncFunctionDef(load_checkpoint) → While → Expr → Call(time.sleep)`,
   - `build_parents(tree)` → the `id(child)→parent` map.

**4. The check loop** — for each of the six checks, `check.run(tree, parents, "server.py")`. Five return `[]`. **CH001 (`BlockingCallInAsync`)** does the work:
   - `ast.walk` reaches the `Call` node `time.sleep(0.1)`.
   - `func` is an `Attribute`; receiver resolves to `"time"`, attr is `"sleep"`.
   - `("time","sleep")` **is** in `_BLOCKING_CALLS`. ✓
   - `is_awaited(node, parents)`? Parent is an `Expr`, not `Await` → not awaited. ✓ (still suspicious)
   - `enclosing_function(node, parents)` climbs `Call→Expr→While→AsyncFunctionDef` → returns the async function; `isinstance(..., AsyncFunctionDef)` is **True**. ✓
   - All conditions met → it builds a `Finding(path="server.py", line=5, col=8, code="CH001", message="`time.sleep()` blocks the event loop inside async function `load_checkpoint`...")`.

**5. Collect & sort** (`scan_path`) — the one finding is collected and sorted by `(path, line, col, code)`.

**6. Render** (`cli.py`, text format) — `f.as_text()` →
```
server.py:5:8: CH001 `time.sleep()` blocks the event loop inside async function `load_checkpoint`; use the async equivalent.
```
plus the summary line `Found 1 issue(s) (CH001: 1)` on stderr, and **exit code 1** (issues found).

## The mental model
```
text → ast.parse → TREE → build_parents → MAP
                          │
        six checks ───────┤ each: walk nodes, ask questions
                          │
        CH001 matches ────► Finding(server.py, 5, 8, CH001, msg)
                          │
        sort ─────────────► as_text() ─► printed line + exit code 1
```

## 🔧 Exercise
Save that `server.py` and run:
```bash
PYTHONPATH=src python3 -m codehound.cli scan server.py
echo "exit: $?"          # 1
PYTHONPATH=src python3 -m codehound.cli scan server.py --format json
```
Now change `time.sleep(0.1)` to `await asyncio.sleep(0.1)` and re-run — zero findings (the `is_awaited` guard). You just watched a false-positive guard work.

## 💬 Interview Q&A
**Q: Walk me through what happens when codehound finds a bug.**
A: (Narrate steps 1–6 above.) Discover file → parse to AST → build parent map → each check walks the tree asking yes/no questions → the matching check emits a Finding → findings are sorted → rendered as `path:line:col: CODE message` with a non-zero exit code.

**Q: At what point would the awaited version stop being flagged?**
A: In CH001's `is_awaited` guard — the call's parent becomes an `Await` node, so the check bails before emitting.

**Q: Which component decides the exit code, and why does it matter?**
A: The CLI: exit 1 if findings exist (unless `--exit-zero`). That's what makes it fail a CI build on a regression.

## ✅ Say this out loud
> *"I can trace a finding end to end: the CLI picks checks and calls scan_path; discovery yields the file; scan_file parses it to an AST and builds the parent map; CH001 walks to the `time.sleep` call, confirms it's a known blocking call, not awaited, and inside an async function, then emits a Finding; scan_path sorts it; the CLI renders `file:line:col: CH001 …` and exits 1. Swap in `await asyncio.sleep` and the is_awaited guard makes it disappear."*

That's Week 2. **You now understand the entire engine.** Next week: the six checks themselves, one bug at a time.
