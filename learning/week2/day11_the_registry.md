# Day 11 — The registry: `ALL_CHECKS` & `get_checks`

> How does codehound know which checks exist, turn them on, and let you pick a subset with `--select`? One list and one function. Open `src/codehound/checks/__init__.py`.

---

## 1. `ALL_CHECKS` — the single source of truth (lines 13–20)
```python
ALL_CHECKS: list[type[Check]] = [
    BlockingCallInAsync,      # CH001
    MutableDefaultArgument,   # CH002
    DeprecatedDatetimeUtcnow, # CH003
    DeprecatedGetEventLoop,   # CH004
    UnclosedFileHandle,       # CH005
    FloatingTask,             # CH006
]
```
A plain list of check **classes** (note `type[Check]` — these are classes, not instances). This is the **registry**: the one place that knows the full set of checks. The `list` command (Day 21) and `get_checks` both read from it. Adding a check = import it + append here. Nothing else in the codebase needs to change.

## 2. `get_checks` — instantiate, optionally filter (lines 23–32)
```python
def get_checks(selected=None):
    if not selected:
        return [cls() for cls in ALL_CHECKS]          # all of them
    wanted = {s.upper() for s in selected}
    out = []
    for cls in ALL_CHECKS:
        if cls.code.upper() in wanted or cls.name.upper() in wanted:
            out.append(cls())
    return out
```
Two behaviors:
- **No selection** → instantiate **every** check (`cls()` turns each class into an object).
- **A selection** (from `--select CH001,CH006`) → keep only checks whose **code** *or* **name** matches, case-insensitively (`.upper()` on both sides). So `--select ch001` and `--select blocking-call-in-async` both work.

`wanted` is a **set** for O(1) membership; comparing `.upper()` on both sides makes matching case-insensitive.

## 3. Classes vs instances — why instantiate at all?
`ALL_CHECKS` holds *classes*; `get_checks` returns *instances* (`cls()`). Checks are currently stateless, so it wouldn't strictly matter — but instantiating means a check *could* hold per-run state (config, counters) without changing the engine. It keeps the door open. The engine always works with `Check` *objects* and calls `.run(...)` on them.

## 4. The registry pattern (interview-worthy)
This is the **registry pattern**: a central collection that maps identifiers (here, codes/names) to implementations (the classes), with a lookup function. It's why codehound is *extensible without modification* of the core — the engine loops over whatever `get_checks` returns and never hardcodes a check.

## 5. 🔧 Exercise
```python
from codehound.checks import ALL_CHECKS, get_checks
print([c.code for c in ALL_CHECKS])           # ['CH001', ..., 'CH006']
print([type(c).__name__ for c in get_checks(["CH001", "ch006"])])
# -> ['BlockingCallInAsync', 'FloatingTask']  (case-insensitive, by code)
print(get_checks(["blocking-call-in-async"])) # also works, by name
```

## 6. 💬 Interview Q&A
**Q: How are checks discovered and run?**
A: A registry list `ALL_CHECKS` holds every check class; `get_checks` instantiates them (all, or a filtered subset), and the engine loops over the instances calling `.run`.

**Q: How does `--select CH001,CH006` work end to end?**
A: The CLI splits the string into codes, passes them to `get_checks`, which keeps only classes whose code or name matches case-insensitively, instantiates those, and returns them.

**Q: Why store classes in `ALL_CHECKS` and instantiate later, rather than store instances?**
A: Lazy instantiation lets a check carry per-run state if needed and keeps construction under `get_checks`'s control. With stateless checks it's a wash, but it's the more extensible choice.

**Q: How would you add a 7th check?**
A: Write a `Check` subclass in its own file, import it here, append it to `ALL_CHECKS`. The engine, CLI, and `--select` pick it up automatically — no other edits.

**Q: What design pattern is this?**
A: The registry pattern — central registration plus a lookup/factory function — which gives open-for-extension, closed-for-modification behavior.

## ✅ Say this out loud
> *"`ALL_CHECKS` is the registry — one list of check classes that's the single source of truth. `get_checks` instantiates them, and with `--select` it filters by code or name case-insensitively using a set for O(1) lookup. Adding a check is a two-line change here; the engine never hardcodes any check, so it's open for extension without modification."*

Tomorrow: integration day — trace one real finding from raw bytes to printed line.
