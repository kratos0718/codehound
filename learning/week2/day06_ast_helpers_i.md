# Day 06 — AST helpers I: `enclosing_function` & `is_awaited`

> Yesterday you built the parent map. Today you use it. These two helpers are how a check asks two questions it constantly needs: *"what function am I inside?"* and *"is this call awaited?"* Open `src/codehound/core.py` lines 100–121.

---

## 1. Why these helpers exist
A check walks the tree and finds a `time.sleep(...)` call. By itself, that call is harmless — `time.sleep` in a normal script is fine. It's only a bug **inside an `async def`**. So the check must look *upward* from the call to its surrounding function. The parent map (Day 5) lets it climb; these helpers wrap that climb in a readable name.

## 2. `enclosing_function` (lines 100–110)
```python
def enclosing_function(node, parents):
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if p is None:
            return None
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return p
        cur = p
    return None
```
Start at `node`, repeatedly hop to the parent, and stop the moment the parent is a function definition (sync `FunctionDef` or `AsyncFunctionDef`). If we reach the top (`p is None`) without finding one, the node is at module level → return `None`.

**Read it as a sentence:** "climb up until you stand inside a function; tell me which one." CH001 then checks `isinstance(fn, ast.AsyncFunctionDef)`; CH005 uses the same helper to know which function "owns" a file handle.

## 3. `is_awaited` (lines 113–121)
```python
def is_awaited(node, parents):
    return isinstance(parents.get(id(node)), ast.Await)
```
One line. Look at the call's *direct* parent — if it's an `await`, the call is awaited.

**Why it matters (the false-positive story):** imagine `await requests.post(...)` where `requests` is actually an *async* HTTP client someone named `requests`. Textually it looks like the blocking `requests.post`, but `await` proves it yields control — it does **not** block the loop. So CH001 calls `is_awaited` and bails. This exact case is a real false positive seen in AutoGPT's MCP client (it's even a test: `test_ch001_ignores_awaited_call_on_sync_named_receiver`).

## 4. 🔧 Exercise
```python
import ast
from codehound.core import build_parents, enclosing_function, is_awaited

tree = ast.parse("async def g():\n    await foo()\n    bar()")
parents = build_parents(tree)
calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
for c in calls:
    fn = enclosing_function(c, parents)
    print(ast.dump(c.func), "awaited?", is_awaited(c, parents),
          "in", type(fn).__name__, getattr(fn, "name", None))
```
Confirm `foo()` reports `awaited? True` and `bar()` reports `False`, both inside the async function `g`.

## 5. 💬 Interview Q&A
**Q: Python's AST has no parent pointers — so how does a check know what function a call is in?**
A: We precompute a `child→parent` map once per file (`build_parents`), then `enclosing_function` walks upward through it until it hits a `FunctionDef`/`AsyncFunctionDef`.

**Q: Why check `is_awaited` before flagging a blocking call?**
A: An awaited call yields control to the event loop, so it isn't blocking — even if its name collides with a sync library. Skipping awaited calls removes a whole class of false positives.

**Q: What's the time complexity of `enclosing_function`?**
A: O(depth of nesting) — it climbs at most the height of the tree from that node, using O(1) dict lookups. Cheap.

**Q: Why return the function *node* rather than just True/False?**
A: So the caller can both test its type (`AsyncFunctionDef`?) and read its `.name` for the error message ("inside async function `load_checkpoint`").

## ✅ Say this out loud
> *"`enclosing_function` walks up the parent map until it finds the nearest function definition, so a check can ask 'am I inside an async def?'. `is_awaited` checks whether a call's direct parent is an `await` node — if so it's non-blocking, which kills the false positive where an async client is coincidentally named like a sync library."*

Tomorrow: the other two helpers — scope-aware `inside_with_statement` and dotted-name resolution.
