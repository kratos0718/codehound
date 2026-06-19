# Day 10 — The package: `__init__.py`, public API & `__all__`

> A short day about an underrated idea: the difference between *code that exists* and *the surface you promise*. Open `src/codehound/__init__.py` (all 22 lines).

---

## 1. What `__init__.py` does
```python
from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import Check, Finding, scan_file, scan_path

__version__ = "0.1.0"

__all__ = ["ALL_CHECKS", "get_checks", "Check", "Finding",
           "scan_file", "scan_path", "__version__"]
```
This file makes `codehound` a **package** and defines its **public API**. Because of these imports, a user can write the clean:
```python
from codehound import scan_path, get_checks      # not codehound.core.scan_path
```
The internal module layout (`core`, `checks`) is hidden behind a tidy front door.

## 2. `__all__` — the curated surface
`__all__` lists the names exported by `from codehound import *`. More importantly, it's a **statement of intent**: "these seven names are the stable, supported API; everything else is internal and may change."

> Think of it like a restaurant: `__all__` is the menu. The kitchen (core.py, the checks) has far more going on, but customers order from the menu. If you rename an internal helper, no user breaks; if you change something in `__all__`, that's a breaking change.

## 3. `__version__` — single source of truth
`__version__ = "0.1.0"` lives here and the CLI imports it for `--version` (Day 21). One place to bump. (It's also declared in `pyproject.toml` — Day 23 — for the packaging metadata.)

## 4. Why this matters for *you*
When you say "I built a tool," a senior may ask "what's its public API?" Being able to point at `__all__` and say "these six functions/classes — `scan_path` for a whole tree, `scan_file` for one file, `get_checks` to pick checks, plus the `Check`/`Finding` types if you want to extend it" shows you think about your code as a *library other people use*, not just a script.

## 5. 🔧 Exercise
```python
import codehound
print(codehound.__version__)          # 0.1.0
print(codehound.__all__)              # the 7 public names
from codehound import scan_path       # works — it's on the menu
# from codehound import build_parents # also importable, but NOT on the menu (internal)
```

## 6. 💬 Interview Q&A
**Q: What is the public API of codehound?**
A: The names in `__all__`: `scan_path`, `scan_file`, `get_checks`, `ALL_CHECKS`, plus the `Check` and `Finding` types and `__version__`. Everything in `core`'s helpers is internal.

**Q: What does `__all__` actually control?**
A: The names pulled in by `from codehound import *`, and by convention it documents the supported surface. It doesn't *prevent* importing internals — it signals what's stable.

**Q: Why re-export from `__init__.py` instead of having users import from `codehound.core`?**
A: It decouples the public API from the internal file layout. I can reorganize modules without breaking users, as long as the names in `__init__` stay put.

**Q: Where does the version live and why one place?**
A: `__version__` in `__init__.py`, imported by the CLI. Single source of truth avoids the classic "version says 0.1 in one place, 0.2 in another" bug. (pyproject mirrors it for packaging.)

## ✅ Say this out loud
> *"`__init__.py` turns the folder into a package and re-exports a small, curated public API via `__all__`, so users import `from codehound import scan_path` without knowing my internal module layout. That decoupling lets me refactor internals freely. `__version__` lives here as the single source of truth and the CLI reads it for `--version`."*

Tomorrow: the registry — how the six checks are discovered, instantiated, and filtered.
