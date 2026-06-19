# Day 18 — CH006: floating-task (fire-and-forget)

> The check behind your open PRs at vLLM, Microsoft (autogen), and OpenAI's Agents SDK. Equivalent to Ruff's RUF006. Open `src/codehound/checks/floating_task.py`.

---

## 1. The bug
```python
asyncio.create_task(do_work())     # result discarded
```
`create_task` / `ensure_future` schedule a coroutine and return a `Task`. But the event loop keeps only a **weak reference** to that task. If *you* don't keep a (strong) reference, the garbage collector can collect the task **before it finishes** — silently cancelling the work mid-flight. No error, no log — the work just vanishes. This is why aborts got dropped in vLLM and error events got dropped in OpenAI's RealtimeSession.

**The fix:** keep a strong reference —
```python
task = asyncio.create_task(do_work())     # assigned → referenced
# or: background = set(); t = asyncio.create_task(...); background.add(t)
#     t.add_done_callback(background.discard)
# or: async with asyncio.TaskGroup() as tg: tg.create_task(...)
```

## 2. The detection (lines 22–58)
The crux is matching **only the discarded form**:
```python
if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
    continue
```
An `ast.Expr` is a statement whose value is **thrown away** — `asyncio.create_task(...)` *on its own line*. If the result were `task = asyncio.create_task(...)` (an `Assign`), `await asyncio.create_task(...)` (inside `Await`), or `return asyncio.create_task(...)`, it would **not** be an `Expr` statement, so we correctly ignore it. That single `isinstance(node, ast.Expr)` test is the whole "is the result discarded?" logic.

Then:
```python
_CREATORS = {"create_task", "ensure_future"}
# func.attr in _CREATORS, receiver is a Name, and:
is_asyncio = owner == "asyncio"
is_loop = "loop" in owner.lower()
if not (is_asyncio or is_loop): continue
```
We match `asyncio.create_task`, `asyncio.ensure_future`, **and** `<loop>.create_task` (any receiver whose name contains "loop", catching `loop.create_task(...)`, `event_loop.create_task(...)`).

## 3. The subtle exclusion: TaskGroup
```python
async def f(tg, coro):
    tg.create_task(coro)        # NOT flagged
```
A `TaskGroup`'s `.create_task` is safe — the group owns and awaits the task. The receiver `tg` doesn't contain "loop" and isn't "asyncio", so the `is_asyncio or is_loop` gate **excludes it**. That's a deliberate false-positive guard, and there's a test for it (`test_ch006_ignores_taskgroup_create_task`).

## 4. The tests (test_checks.py 148–172)
- flags a discarded `asyncio.create_task(coro)` ✓
- ignores `t = asyncio.create_task(coro); await t` (referenced) ✓
- ignores `tg.create_task(coro)` (TaskGroup) ✓

## 5. 💬 Interview Q&A
**Q: Why is `asyncio.create_task(x())` on its own line a bug?**
A: The loop holds only a weak reference to the task, so if nothing else references it, the GC can collect it before it completes — silently dropping the work.

**Q: How do you tell a discarded task from a kept one?**
A: A discarded call is an `ast.Expr` statement (its value is thrown away). If it's assigned, awaited, or returned, it isn't an `Expr` statement, so I skip it — that one check *is* the discard test.

**Q: How do you avoid flagging `TaskGroup.create_task`?**
A: I only match receivers that are `asyncio` or contain "loop". A `tg.create_task` receiver is neither, so it's excluded — and that's covered by a test.

**Q: What are the correct fixes?**
A: Keep a strong reference: assign it, await it, store it in a set with a done-callback to discard, or use `asyncio.TaskGroup`.

**Q: Any false negatives?**
A: If someone names their loop variable something without "loop" in it (e.g. `el.create_task`), the heuristic misses it. Name-based, like the rest — a precision tradeoff.

## ✅ Say this out loud
> *"CH006 flags fire-and-forget tasks — `asyncio.create_task(...)` whose result is discarded. The key is that a discarded call is an `ast.Expr` statement; if it's assigned, awaited, or returned it isn't, so I skip it. I match `asyncio.*` and `<loop>.create_task`, but exclude `TaskGroup.create_task` because the group owns the task. The loop only holds a weak ref, so discarded tasks can be GC'd mid-run — that's the bug under review at vLLM, Microsoft, and OpenAI."*

Tomorrow: zoom out — the shared contract and the precision-over-recall philosophy that ties all six together.
