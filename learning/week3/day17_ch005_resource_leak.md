# Day 17 — CH005: unclosed-file-handle

> The most sophisticated check — it has to *track* a variable across a function and reason about escape hatches. Merged into agno. Open `src/codehound/checks/resource_leak.py`.

---

## 1. The bug
```python
def load(path):
    fh = open(path)          # opened...
    return fh.read()         # ...never closed
```
Every `open()` returns a file descriptor — an OS resource with a hard limit (`RLIMIT_NOFILE`, ~1024). If you don't close it, it leaks. One call is fine; in a **loop** (e.g. an agent transcribing audio repeatedly) you slowly exhaust descriptors and crash with "too many open files" — *hours* after the real mistake. CPython's GC eventually reclaims it, but only when the object dies, which may be never if it's stored on a long-lived attribute. **The fix:** `with open(path) as fh:` (auto-closes, even on exceptions).

## 2. The detection — and its three escape hatches (lines 56–95)
For each `Assign` whose value is a direct `open(...)`:
1. **Skip if `inside_with_statement`** → a `with` already manages it. (Day 7)
2. Collect the assigned name(s), handling tuple/list unpacking via `_name_targets`.
3. **Must be inside a function** (`enclosing_function`) — function scope is where close-tracking is reliable; module-level opens are skipped.
4. **Escape hatch A — `returns_handle`:**
```python
returns_handle = any(isinstance(n, ast.Return) and isinstance(n.value, ast.Name)
                     and n.value.id in names for n in ast.walk(fn))
```
If the function **returns** the handle, the *caller* owns closing it — not a leak here.
5. **Escape hatch B — `_has_close_call(fn, name)`:** if `name.close()` appears anywhere in the function, it's handled.
6. Only if **neither** hatch applies → emit "`name = open(...)` is never closed; use `with`."

## 3. Why this check is "harder"
The others match a single node in isolation. CH005 must reason about a **variable's lifetime within a scope**: was it wrapped, returned, or closed *anywhere* in the function? That's a (small, intraprocedural) **data-flow** question, approximated by walking the whole function body for `.close()` and `return`. It's deliberately conservative — when in doubt, it stays quiet, favoring precision.

## 4. The honest limits
- It only tracks the **simple** `fh = open(...)` form, not `self.fh = open(...)` (attribute targets) or a handle passed into another function that closes it. Those are skipped to avoid false positives.
- It's **intraprocedural** — it can't follow the handle into a helper. Conservative by design.

## 5. The tests (test_checks.py 125–142) — note the negatives
- flags `fh = open(p); return fh.read()` (leak) ✓
- ignores `with open(p) as fh:` ✓
- ignores explicit `fh.close()` ✓
- ignores a **returned** handle (`return fh`) ✓

The three "ignores" are the false-positive guards in action.

## 6. 💬 Interview Q&A
**Q: Why is an unclosed file a real bug and not a nitpick?**
A: File descriptors are a capped OS resource. In a loop you exhaust them and crash with "too many open files," often long after the offending line — a nasty production failure. GC isn't guaranteed to save you if the handle is held by a long-lived object.

**Q: How do you avoid false positives here?**
A: Three guards — skip if it's inside a `with`, skip if the function returns the handle (caller owns it), and skip if there's a matching `.close()` anywhere in the function. When unsure, I don't flag.

**Q: This needs more than matching one node — what's different?**
A: It's a small intraprocedural data-flow problem: I track the assigned name across the function body looking for a `return` or `.close()`. The others are local; this reasons about a variable's lifetime in its scope.

**Q: What does it miss?**
A: Attribute targets like `self.fh = open(...)`, and handles passed to a helper that closes them — both skipped to stay precise. It's conservative on purpose.

## ✅ Say this out loud
> *"CH005 flags `fh = open(...)` that's never closed. It finds open-assignments not inside a `with`, scoped to a function, then clears them if the function returns the handle or calls `.close()` anywhere — so it's a small intraprocedural data-flow check, not just node matching. It's conservative: attribute targets and cross-function handoffs are skipped to avoid false positives. I fixed one of these in agno's audio transcription."*

Tomorrow: CH006 — the fire-and-forget task, the bug under review at vLLM, Microsoft, and OpenAI.
