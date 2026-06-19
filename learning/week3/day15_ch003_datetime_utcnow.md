# Day 15 — CH003: deprecated `datetime.utcnow()`

> A correctness *and* deprecation bug. Fixed across crewAI's memory subsystem (9 call sites). Open `src/codehound/checks/datetime_utcnow.py`.

---

## 1. The bug
```python
datetime.utcnow()              # returns a NAIVE datetime
```
`utcnow()` (and `utcfromtimestamp()`) return a datetime with **no timezone attached** (`tzinfo=None`) — but the values are UTC. So you get an object that holds UTC numbers while *claiming* (by being naive) to be local time. Compare it with an aware datetime and you get errors or silent wrong math. It's a long-standing footgun, **deprecated since Python 3.12** and slated for removal.

**The fix:** `datetime.now(timezone.utc)` — an *aware* UTC datetime. (For a naive-UTC drop-in: `datetime.now(timezone.utc).replace(tzinfo=None)`.)

## 2. The detection (lines 20–52)
```python
_DEPRECATED = {"utcnow", "utcfromtimestamp"}
```
For each `Call`:
1. `func` must be an `Attribute` whose `attr` is in `_DEPRECATED`.
2. The receiver must be `datetime` — either a `Name` (`datetime.utcnow()`) **or** an `Attribute` ending in `datetime` (`dt.datetime.utcnow()` / `import datetime; datetime.datetime.utcnow()`):
```python
target_ok = (isinstance(value, ast.Name) and value.id == "datetime") or \
            (isinstance(value, ast.Attribute) and value.attr == "datetime")
```
3. Emit a Finding suggesting `datetime.now(timezone.utc)`.

## 3. Why match both `datetime.x` and `something.datetime.x`?
People import it two ways: `from datetime import datetime` → `datetime.utcnow()`, or `import datetime` → `datetime.datetime.utcnow()`. Checking that the *immediate* receiver is named `datetime` (as a Name or the tail of an Attribute) covers both common idioms with one rule.

## 4. The tests (test_checks.py 99–106)
- flags `datetime.utcnow()` ✓
- ignores `datetime.now(timezone.utc)` ✓

## 5. 💬 Interview Q&A
**Q: What's actually wrong with `datetime.utcnow()`?**
A: It returns a *naive* datetime holding UTC values, so the object lies about its timezone. Mixing it with aware datetimes causes wrong comparisons or exceptions. It's also deprecated in 3.12.

**Q: What's the correct replacement?**
A: `datetime.now(timezone.utc)` for an aware UTC datetime; if you truly need naive, append `.replace(tzinfo=None)` so the intent is explicit.

**Q: How do you catch both import styles?**
A: I check that the call's immediate receiver is named `datetime` — either a bare `Name` or the `.datetime` tail of an attribute chain — which covers `from datetime import datetime` and `import datetime`.

**Q: Is this a correctness bug or just a deprecation warning?**
A: Both. The naive-UTC behavior is a real correctness footgun *today*, and 3.12 deprecates it, so fixing it is future-proofing plus a bug fix.

## ✅ Say this out loud
> *"CH003 flags `datetime.utcnow()` / `utcfromtimestamp()`. They return naive datetimes that hold UTC values but carry no tzinfo, which breaks comparisons and is deprecated in 3.12. I match calls whose method is utcnow/utcfromtimestamp and whose receiver is `datetime` in either import style, and suggest `datetime.now(timezone.utc)`. I fixed nine of these across crewAI's memory code."*

Tomorrow: CH004 — the deprecated event-loop API, *and* the honest story of its false positive.
