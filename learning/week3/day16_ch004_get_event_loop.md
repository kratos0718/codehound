# Day 16 — CH004: deprecated `asyncio.get_event_loop()`

> The most *nuanced* check — and the one with a known false positive. Knowing *why* it's imperfect is more impressive than pretending it's perfect. Open `src/codehound/checks/get_event_loop.py`.

---

## 1. The bug
`asyncio.get_event_loop()` was the old way to get the loop. Since Python 3.10 it's **deprecated when called with no running loop** (and emits a `DeprecationWarning` from 3.12), because its behavior there is surprising — it may create a new loop or error depending on context. The modern替代:
- Inside a coroutine: `asyncio.get_running_loop()`.
- To run a coroutine from sync code: `asyncio.run(...)`.

Fixed in crewAI's structured-tool / Snowflake search tool.

## 2. The detection (lines 18–47)
The simplest check in the codebase:
```python
if (isinstance(func, ast.Attribute)
        and func.attr == "get_event_loop"
        and isinstance(func.value, ast.Name)
        and func.value.id == "asyncio"):
    # flag it
```
Match any `asyncio.get_event_loop()` call. That's it — no context climb.

## 3. The honest limitation (THIS is the interview gold)
`get_event_loop()` is **only** deprecated when there's *no running loop*. **Inside** a running coroutine it returns the running loop and is *not* deprecated. CH004 doesn't distinguish that context — it flags *all* calls. So it can **false-positive** on a legitimate in-loop call.

This actually happened: a maintainer **rejected** one of these PRs, pointing out the call was inside a running loop. That rejection isn't a failure — it's a finding. It taught me the difference between:
- a **lint rule** (a heuristic that's often right), and
- **ground truth** (what's actually a bug in *this* context).

It became material for RQ4 in my paper (precision vs. recall, and where static heuristics break).

## 4. Could you fix the false positive?
Partially. You could require the call to be **outside** any `async def` (using `enclosing_function`) to approximate "no running loop" — but that's still imperfect, because sync code can be *called from* a running loop at runtime, which the AST can't see. True precision needs runtime/flow information a static tool doesn't have. **Naming that boundary is the whole point.**

## 5. The tests (test_checks.py 112–119)
- flags `asyncio.get_event_loop()` ✓
- ignores `asyncio.get_running_loop()` ✓

## 6. 💬 Interview Q&A
**Q: When is `asyncio.get_event_loop()` actually a problem?**
A: When called with no running loop — deprecated since 3.10. Inside a running coroutine it's fine, which is exactly the case my check can't distinguish.

**Q: So your check has a false positive — isn't that bad?**
A: It's a known, documented limitation. A maintainer rejected one PR for this reason, and I treat that as signal: the AST can't see the *runtime* loop context, so a purely static rule will over-flag. I'd rather be honest about precision than pretend it's perfect.

**Q: How would you reduce the false positive?**
A: Approximate "no running loop" by only flagging calls outside any `async def`. It helps but isn't sound, because sync functions can be invoked from a running loop at runtime — static analysis fundamentally can't resolve that.

**Q: What did you learn from the rejection?**
A: The difference between a lint heuristic and ground truth, and that a rejected PR is data, not just a loss — it's in my paper's discussion of precision.

## ✅ Say this out loud
> *"CH004 flags `asyncio.get_event_loop()`, deprecated since 3.10 when there's no running loop. My check flags all calls, which means it can false-positive inside a running coroutine where the call is valid — a maintainer rejected one PR for exactly that. I keep it because it's usually right and the limitation is instructive: distinguishing the two cases needs runtime context an AST doesn't have. That nuance is in my paper."*

Tomorrow: CH005 — the unclosed file handle, the most sophisticated check.
