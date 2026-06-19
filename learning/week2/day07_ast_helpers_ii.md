# Day 07 — AST helpers II: `inside_with_statement` & `attr_call_parts`

> Two more helpers. One answers "is this safely inside a `with` block?" (with a subtle scope rule). The other turns `a.b.c()` into `("a.b", "c")` so checks can match dotted names. Open `core.py` lines 124–162.

---

## 1. `inside_with_statement` (lines 124–137)
```python
def inside_with_statement(node, parents):
    cur = node
    while cur is not None:
        p = parents.get(id(cur))
        if p is None:
            return False
        if isinstance(p, (ast.With, ast.AsyncWith)):
            return True
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            return False
        cur = p
    return False
```
Like yesterday's climb, but with **two stop conditions**:
- Hit a `With`/`AsyncWith` first → `True` (we're managed by a context manager).
- Hit a **function/class/module boundary** first → `False`.

**The subtle part — why the boundary check?** Without it, you could be inside function `B` which happens to be *defined inside* a `with` block in function `A`. That outer `with` doesn't manage *your* file handle. Stopping at the function boundary prevents wrongly crediting a `with` from an unrelated outer scope. CH005 uses this to skip `with open(...) as f:` correctly.

## 2. `attr_call_parts` (lines 140–162)
```python
def attr_call_parts(node):
    # a.b()      -> ("a", "b")
    # a.b.c()    -> ("a.b", "c")
    # foo()      -> (None, None)
```
A call's `func` can be a plain `Name` (`foo()`) or an `Attribute` (`a.b()`). For attribute calls we want the **receiver** and the **method** separately, so a check can match `("time", "sleep")` or `("urllib.request", "urlopen")`.

The tricky case is a **dotted** receiver like `urllib.request.urlopen`. In the AST that's nested `Attribute` nodes. The helper walks *down* the nesting collecting names (`request`, `urllib`), then reverses them into `"urllib.request"`:
```python
parts = []
cur = value
while isinstance(cur, ast.Attribute):
    parts.append(cur.attr)
    cur = cur.value
if isinstance(cur, ast.Name):
    parts.append(cur.id)
return ".".join(reversed(parts)), attr
```
> Note: CH001 actually *inlines* this same dotted-resolution logic rather than importing the helper — a small duplication you could refactor (good "what would you improve?" answer).

## 3. Why string-matching names is "good enough" (and its limit)
codehound matches on *names* (`requests`, `time`), not on what those names truly resolve to. If someone does `import requests as r` and calls `r.get(...)`, the name is `r` and the check misses it. That's a deliberate tradeoff: real type/import resolution needs a full semantic pass (like mypy). Name-matching catches the overwhelmingly common case with ~50 lines. **Knowing this limit is interview gold.**

## 4. 🔧 Exercise
```python
import ast
from codehound.core import build_parents, inside_with_statement, attr_call_parts

code = "def f(p):\n    with open(p) as fh:\n        urllib.request.urlopen(p)\n"
tree = ast.parse(code); parents = build_parents(tree)
for n in ast.walk(tree):
    if isinstance(n, ast.Call):
        print(attr_call_parts(n), "in with?", inside_with_statement(n, parents))
```
You'll see `('urllib.request', 'urlopen')` and `in with? True`.

## 5. 💬 Interview Q&A
**Q: Why does `inside_with_statement` stop at function/class boundaries?**
A: A `with` block in an *outer* scope doesn't manage a resource opened in an inner function. Stopping at the boundary avoids falsely treating an unrelated outer `with` as protection.

**Q: How do you handle a dotted module like `urllib.request.urlopen`?**
A: It's nested `Attribute` nodes; I walk down collecting the attribute names, then reverse them into a dotted string to match against my known-bad set.

**Q: A user writes `import requests as r; r.get()`. Does codehound catch it?**
A: No — it matches names, not resolved imports. That's an intentional simplicity tradeoff; full import resolution would need a semantic analysis pass. It catches the common, idiomatic usage.

**Q: You said CH001 inlines the dotted logic instead of using `attr_call_parts`. What would you do?**
A: Refactor CH001 to call the shared helper — removes duplication and a place for the two copies to drift.

## ✅ Say this out loud
> *"`inside_with_statement` walks up but stops at the enclosing function/class/module so an outer `with` can't be mistaken for protection of an inner resource. `attr_call_parts` splits an attribute call into receiver and method, handling dotted modules by walking the nested Attribute nodes. Both feed the name-based matching the checks rely on — simple, fast, and limited to literal names, which is a conscious tradeoff."*

Tomorrow: how codehound finds the files to scan — and the one-line trick that makes `os.walk` skip folders.
