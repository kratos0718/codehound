# Day 08 — File discovery: `iter_python_files` & the skip-dirs trick

> Before codehound can analyze anything, it has to *find* the `.py` files — and just as importantly, *avoid* the wrong ones. Open `core.py` lines 18–44 and 168–177.

---

## 1. `DEFAULT_SKIP_DIRS` (lines 18–44)
A `frozenset` of directory names we never descend into:
- **VCS & caches:** `.git`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`
- **Dependencies:** `node_modules`, `site-packages`, `venv`, `.venv`, `vendor`
- **Build output:** `dist`, `build`
- **And deliberately:** `tests`, `test`, `examples`, `cookbook`, `docs`

**Why skip `tests/` and `examples/`?** They *intentionally* contain bad patterns. A test for the mutable-default check literally writes `def f(x=[])`. If codehound flagged those, every project would drown in false noise. (`--include-tests` re-enables them — Day 21.)

**Why `frozenset`?** Immutable (safe as a module-level shared default — nobody can accidentally mutate it) and O(1) membership lookup.

## 2. `iter_python_files` (lines 168–177)
```python
def iter_python_files(root, skip_dirs=DEFAULT_SKIP_DIRS):
    if os.path.isfile(root):
        if root.endswith(".py"):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if fname.endswith(".py"):
                yield os.path.join(dirpath, fname)
```
Two modes:
- **Single file:** if `root` is a file, yield it (if `.py`) and stop.
- **Directory:** walk it recursively, yielding every `.py`.

It's a **generator** (`yield`) — it streams paths one at a time instead of building a giant list, so memory stays flat even on huge repos.

## 3. The one-line magic: `dirnames[:] = [...]`
```python
dirnames[:] = [d for d in dirnames if d not in skip_dirs]
```
`os.walk` hands you `dirnames` (the subfolders of the current dir) and — crucially — **reads that same list to decide where to recurse next.** By overwriting its *contents in place* (`[:]`), you prune branches before `os.walk` descends into them. Skip `node_modules` here and os.walk never even opens it — fast.

**The trap:** `dirnames = [...]` (no `[:]`) would rebind your local variable to a new list and leave the one os.walk holds untouched — pruning would silently do nothing. The `[:]` is load-bearing.

## 4. 🔧 Exercise
```python
from codehound.core import iter_python_files
for p in iter_python_files("src"):
    print(p)              # only src/codehound/*.py — no caches, no tests
```
Then create a `node_modules/x.py` next to it and confirm it's *not* listed.

## 5. 💬 Interview Q&A
**Q: How does codehound avoid scanning dependencies and generated code?**
A: A `frozenset` of skip-dir names, pruned in `os.walk` via `dirnames[:] = [...]`, so it never recurses into them.

**Q: Why `dirnames[:] = ...` instead of `dirnames = ...`?**
A: `os.walk` reuses the *same* list object to choose recursion. Slice-assignment mutates it in place; plain assignment rebinds a local and the prune is ignored.

**Q: Why skip `tests/` by default? Isn't test code worth checking?**
A: Tests deliberately contain bad patterns as fixtures, so they're mostly false positives. I skip them by default but expose `--include-tests` for when you do want them.

**Q: Why a generator instead of returning a list?**
A: Streaming paths keeps memory constant on large repos and lets scanning start before discovery finishes.

**Q: Why `frozenset` over a `set` or `list`?**
A: Immutable (safe shared default) and O(1) lookups vs O(n) for a list.

## ✅ Say this out loud
> *"`iter_python_files` is a generator that yields every `.py` under a path. It prunes junk and test/example folders by mutating `os.walk`'s `dirnames` list in place with slice assignment — `dirnames[:] = ...` — which is the part people get wrong, because plain reassignment doesn't affect os.walk's recursion. Skip dirs live in a frozenset for O(1) immutable lookups."*

Tomorrow: turning a found file into findings — `scan_file` and `scan_path`.
