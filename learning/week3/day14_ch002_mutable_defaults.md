# Day 14 — CH002: mutable-default-argument

> The most *common* bug codehound finds (54% of frameworks in the paper). Merged into agno and mem0. Open `src/codehound/checks/mutable_defaults.py`. Equivalent to Ruff's B006.

---

## 1. The bug
```python
def add_item(item, basket=[]):     # ← trap
    basket.append(item)
    return basket
```
The default `[]` is evaluated **once, when the function is defined** — not per call. So *every* call that relies on the default shares the **same** list object:
```python
add_item("a")    # ['a']
add_item("b")    # ['a', 'b']   ← leaked from the previous call!
```
State bleeds across unrelated calls. No error, no crash — just baffling behavior. **The fix:** default to `None` and build the container inside the body:
```python
def add_item(item, basket=None):
    if basket is None:
        basket = []
```

## 2. The detection (lines 20–53)
```python
_MUTABLE_FACTORIES = {"list","dict","set","Counter","defaultdict","OrderedDict","deque"}

def _is_mutable_default(node):
    if isinstance(node, (ast.List, ast.Dict, ast.Set)):   # [] {} {1,2}
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id in _MUTABLE_FACTORIES           # list() dict() ...
    return False
```
Two mutable forms are caught: **literals** (`ast.List`/`Dict`/`Set`) and **factory calls** (`list()`, `dict()`, `defaultdict(...)`, etc.).

`run` iterates every function and inspects its defaults:
```python
defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
```
Why both? `args.defaults` covers normal positional/keyword params; `args.kw_defaults` covers **keyword-only** params (after a `*`), and those can be `None` (meaning "no default"), which we filter out. The finding points at the **default's own line/col** so the fix location is precise.

## 3. Why not flag tuples or frozensets?
`()` and `frozenset()` are **immutable** — sharing them is harmless. So they're deliberately absent from the detection. CH002 only cares about *mutable* containers, because only mutation leaks state.

## 4. The tests (test_checks.py 80–93)
- flags `def f(x=[])` ✓
- flags `def f(x=dict())` (factory form) ✓
- ignores `def f(x=None)` (the correct pattern) ✓

## 5. 💬 Interview Q&A
**Q: Why is `def f(x=[])` dangerous?**
A: The default list is created once at definition time and shared across all calls, so mutations persist between unrelated calls. The fix is `x=None` plus building the list in the body.

**Q: How do you detect both `[]` and `list()`?**
A: `[]`/`{}`/`set()` literals are `ast.List`/`Dict`/`Set` nodes; factory forms are `Call` nodes whose function name is in a known set (`list`, `dict`, `defaultdict`, ...).

**Q: What are `kw_defaults` and why filter `None`?**
A: They're defaults for keyword-only args (after `*`). The list aligns positionally with the kw-only args and uses `None` to mean "no default," so I drop the `None` entries.

**Q: Why not flag a tuple default?**
A: Tuples and frozensets are immutable — sharing them can't leak state — so they're intentionally not flagged.

**Q: Could this false-positive?**
A: Rarely — e.g. if someone *intentionally* uses a shared mutable default as a cache. It's still a code smell, and B006 flags it too, so I match the established convention.

## ✅ Say this out loud
> *"CH002 flags mutable default arguments — list/dict/set literals or their factory calls used as a parameter default. They're created once at definition time and shared across calls, leaking state. I scan each function's `defaults` and non-None `kw_defaults`, and report the default's exact location. Tuples/frozensets are skipped because immutables can't leak. It's Ruff's B006, and I fixed these in agno and mem0."*

Tomorrow: CH003 — `datetime.utcnow()`, the timestamp that lies.
