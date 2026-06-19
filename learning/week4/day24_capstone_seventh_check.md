# Day 24 — Capstone: write your own 7th check

> The real test of understanding: can you *extend* it? Today you add a brand-new check, end to end, the same way you'd add a feature to any tool. If you can do this unaided, you own codehound.

---

## 1. The check we'll build: CH007 — `bare-except`
**The bug:** `except:` (or `except Exception:` swallowing everything) with no re-raise hides errors — including `KeyboardInterrupt` and real failures — making bugs invisible. A focused, defensible rule. We'll flag a **bare `except:`** (catches *everything*, including system-exit signals).

## 2. Step 1 — the check file
Create `src/codehound/checks/bare_except.py`:
```python
"""CH007 - Bare `except:` clause swallows all exceptions, including
KeyboardInterrupt/SystemExit, and hides real errors. Catch specific
exceptions instead, e.g. `except ValueError:`."""
from __future__ import annotations
import ast
from codehound.core import Check, Finding


class BareExcept(Check):
    code = "CH007"
    name = "bare-except"
    description = "Bare `except:` catches everything and hides errors; catch specific exceptions."

    def run(self, tree, parents, path):
        findings = []
        for node in ast.walk(tree):
            # ast.ExceptHandler with type=None is a bare `except:`
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                findings.append(
                    Finding(
                        path=path,
                        line=node.lineno,
                        col=node.col_offset,
                        code=self.code,
                        message="bare `except:` swallows all exceptions; catch a specific type.",
                    )
                )
        return findings
```
Notice it's the **same skeleton** as the other six: walk → filter by node type (`ExceptHandler`) → condition (`type is None`) → emit a `Finding`. You didn't invent anything — you filled in the contract.

## 3. Step 2 — register it
In `src/codehound/checks/__init__.py`:
```python
from codehound.checks.bare_except import BareExcept     # add import
...
ALL_CHECKS = [ ..., FloatingTask, BareExcept ]           # append
```
That's the *only* wiring. The engine, CLI, `--select CH007`, and `list` all pick it up automatically (Day 11's payoff).

## 4. Step 3 — test it (positive + negative, Day 22 style)
Add to `tests/test_checks.py`:
```python
def test_ch007_flags_bare_except():
    code = "try:\n    x()\nexcept:\n    pass\n"
    assert len(_run(code, ["CH007"])) == 1

def test_ch007_ignores_specific_except():
    code = "try:\n    x()\nexcept ValueError:\n    pass\n"
    assert _run(code, ["CH007"]) == []
```
Run `pytest -q` → green. You've shipped a check *with* its precision proof.

## 5. Step 4 — try it
```bash
PYTHONPATH=src python3 -m codehound.cli list                  # CH007 now listed
PYTHONPATH=src python3 -m codehound.cli scan somefile.py --select CH007
```

## 6. The lesson
Adding a check touched **three files** (the check, the registry, the tests) and **zero** lines of the engine or CLI. That's the architecture paying off: *open for extension, closed for modification.* When an interviewer asks "how extensible is it?", this is your answer — and you've actually done it.

## 7. 💬 Interview Q&A
**Q: How would you add a new rule to codehound?**
A: Write a `Check` subclass with `code`/`name`/`description` and a `run` that walks the AST for the pattern, import it in the registry and append to `ALL_CHECKS`, and add a positive + negative test. The engine and CLI need no changes.

**Q: How long did adding the 7th check take / what did it touch?**
A: Three files — the new check, one import+append in the registry, two tests. No engine or CLI edits, which is the whole point of the contract + registry design.

**Q: How did you pick the `ExceptHandler` node?**
A: A bare `except:` is an `ast.ExceptHandler` with `type is None`; a typed `except ValueError:` has a non-None `type`. So the condition is just `node.type is None`.

**Q: What would make CH007 more precise?**
A: Skip handlers that re-raise (`raise` with no args in the body) — those bare-excepts are intentional. That'd be a false-positive guard, exactly like the others.

## ✅ Say this out loud
> *"To prove I own it, I added a seventh check — CH007, bare-except. It's the same skeleton as the rest: walk the tree for `ExceptHandler` nodes with no type, emit a Finding. Registering it was one import and one append; I added a positive and a negative test. Zero engine or CLI changes — that's the open-for-extension design working. If I wanted more precision I'd skip handlers that re-raise."*

Tomorrow: the finale — the full interview script and the design tradeoffs that make you unshakeable.
