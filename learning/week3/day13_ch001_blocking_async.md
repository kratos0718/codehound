# Day 13 — CH001: blocking-call-in-async

> The flagship check — the one that got merged into unsloth (40k★) and agno. Open `src/codehound/checks/blocking_async.py`.

---

## 1. The bug (understand it deeply)
An `async def` runs on an **event loop** that switches between coroutines *only at `await` points*. A synchronous, blocking call — `time.sleep(30)`, `requests.get(...)`, `subprocess.run(...)` — has no `await`, so it **holds the loop hostage** for its entire duration. Every other request, task, and the agent loop itself freezes. In unsloth, a `time.sleep` in an async model-export route stalled the server for up to 30 seconds with zero concurrency.

The fix is the async equivalent: `await asyncio.sleep(...)`, an async HTTP client (`httpx.AsyncClient`), or pushing the blocking call off-loop with `await asyncio.to_thread(...)` / `loop.run_in_executor(...)`.

## 2. The detection (lines 38–87)
```python
_BLOCKING_CALLS = {("time","sleep"), ("requests","get"), ("requests","post"),
                   ..., ("subprocess","run"), ("os","system"),
                   ("urllib.request","urlopen")}
```
A curated set of `(module, method)` pairs known to block. The `run` method:
1. Node must be a `Call` whose `func` is an `Attribute` (we only match `module.method(...)` forms).
2. Resolve the receiver to a module name, handling dotted prefixes like `urllib.request`.
3. `(module, attr)` must be in `_BLOCKING_CALLS`.
4. **`is_awaited`? → skip** (false-positive guard, Day 6).
5. **`enclosing_function` must be an `AsyncFunctionDef`** — blocking in a *sync* function is normal and fine.
6. Emit a Finding naming the call and the function.

## 3. Why each guard exists
- **Attribute-only:** we match `time.sleep`, not a bare `sleep()` — too ambiguous to know what a bare name is.
- **`is_awaited` skip:** `await x.post(...)` yields, so it's safe even if `x` is named like a sync lib. (Real false positive in AutoGPT.)
- **async-only:** the *exact same call* is a bug in async and a non-issue in sync. Context is everything — this is why a regex grep for `time.sleep` would be useless.

## 4. The tests that prove it (test_checks.py 27–74)
- flags `time.sleep` in `async def` ✓
- ignores `time.sleep` in a **sync** `def` ✓
- ignores `await requests.post(...)` where `requests` is an async client ✓
- still flags an **unawaited** `requests.get` in async ✓
- ignores `await asyncio.sleep(1)` ✓

## 5. 💬 Interview Q&A
**Q: What exactly goes wrong with `time.sleep` in an async function?**
A: It blocks the single event-loop thread for its whole duration, so every other coroutine and the loop itself stall. There's no yield point, so nothing else can run.

**Q: How do you avoid flagging `await asyncio.sleep` or an awaited async client?**
A: The `is_awaited` guard: if the call's parent is an `Await`, it yields to the loop and isn't blocking, so I skip it.

**Q: Why not just grep for `time.sleep`?**
A: Grep can't tell sync from async context, can't see `await`, and would flag comments and strings. The bug is *contextual* — it needs the AST and the enclosing-function climb.

**Q: How do you decide what counts as "blocking"?**
A: A curated allowlist of known-blocking `(module, method)` pairs — the standard offenders (`time.sleep`, `requests.*`, `subprocess.*`, `os.system`, `urllib`). It's precision-first; I'd rather miss an exotic one than cry wolf.

**Q: What's a known false negative?**
A: Aliased imports (`import requests as r; r.get()`) — name-based matching misses `r`. Accepted tradeoff for simplicity.

## ✅ Say this out loud
> *"CH001 flags a known blocking call — `time.sleep`, `requests.get`, etc. — when it's directly inside an `async def` and not awaited. It walks each call, resolves the dotted module name, checks it against an allowlist, skips awaited calls, and confirms the enclosing function is async. That context-sensitivity is why it needs an AST, not a grep. It's the check that got merged into unsloth and agno."*

Tomorrow: CH002 — the mutable default argument, a 30-year-old Python footgun.
