# Day 04 — `Finding` & `Check`: the contract

> Today you learn the two small classes that everything else is built around. They define the **contract**: what a check receives, and what it must produce. Master these and the whole architecture clicks. Open `src/codehound/core.py` lines 47–81 alongside this.

---

## 1. Why a "contract" at all?

codehound has six checks today and you'll add a seventh on Day 24. Imagine if each check returned results in its own format — one returns strings, one returns tuples, one prints directly. The engine and CLI would need special-case code for each. Chaos.

Instead, codehound defines a **contract** — a shared agreement:
- Every check **receives** the same three things: the AST `tree`, the `parents` map, and the file `path`.
- Every check **returns** the same thing: a `list[Finding]`.

Because every check obeys this, the engine can treat them all identically (`core.py` line 192):

```python
for check in checks:
    findings.extend(check.run(tree, parents, path))
```

That loop doesn't know or care *which* checks exist. Add a 100th check and this line never changes. **That's the payoff of a contract.**

## 2. `Finding` — the unit of output (core.py lines 47–67)

```python
@dataclass(frozen=True)
class Finding:
    """A single rule violation at a specific source location."""
    path: str
    line: int
    col: int
    code: str
    message: str
```

A `Finding` is one bug at one location. Five fields — and you've seen them: they're exactly the pieces of the output line `path:line:col: CODE message`. Let's unpack the decorators and choices.

### `@dataclass` — auto-generated boilerplate
Normally a class needs an `__init__` to accept and store fields:
```python
class Finding:
    def __init__(self, path, line, col, code, message):
        self.path = path
        self.line = line
        ...
```
`@dataclass` writes that `__init__` *for you* from the field annotations. It also generates `__repr__` (nice printing) and `__eq__` (so two findings with the same values are equal — important for the tests on Day 22). You just declare the fields; the decorator does the plumbing.

### `frozen=True` — immutable
`frozen=True` makes instances **read-only**: once created, you can't do `finding.line = 5` (it raises). Why make findings immutable?
1. **Safety** — a finding is a *fact* ("there's a bug here"). Facts shouldn't be mutated after the fact by some later code.
2. **Hashability** — frozen dataclasses are hashable, so findings can go in sets / be deduplicated if ever needed.
3. **Clarity** — it signals intent: this is a value object, not a thing with behavior.

> ✅ **Line:** *"`Finding` is a frozen dataclass — an immutable value object holding the five fields of a result. Frozen because a finding is a fact; nothing should mutate it after creation, and it makes findings hashable and comparable, which the tests rely on."*

### The two methods — `as_text` and `as_dict` (lines 57–67)
```python
def as_text(self) -> str:
    return f"{self.path}:{self.line}:{self.col}: {self.code} {self.message}"

def as_dict(self) -> dict:
    return {"path": self.path, "line": self.line, ...}
```
The `Finding` knows how to render *itself* in two formats: a one-line string (for human/text output) and a dict (which the CLI turns into JSON, Day 21). This keeps formatting knowledge *with the data* — the CLI doesn't need to know a finding's internal field names to print it. A small example of good encapsulation.

## 3. `Check` — the base class every rule inherits (core.py lines 70–81)

```python
class Check:
    """Base class for a single static-analysis rule."""
    code: str = ""
    name: str = ""
    description: str = ""

    def run(self, tree: ast.AST, parents: dict, path: str) -> list[Finding]:
        raise NotImplementedError
```

This is the **interface** half of the contract. It says: "to be a check, you must have a `code`, `name`, `description`, and a `run(tree, parents, path)` method that returns findings."

### Why a base class?
Three reasons, all interview-worthy:

1. **It documents the contract in code.** Anyone writing a new check inherits `Check` and immediately knows the shape they must fill in.
2. **`raise NotImplementedError`** is a deliberate trap: if you subclass `Check` but forget to write `run`, calling it fails loudly with a clear error instead of silently doing nothing. It forces every subclass to implement the method.
3. **The class attributes (`code`, `name`, `description`)** mean each check is *self-describing*. The `list` command (Day 21) just reads `cls.code` and `cls.description` off each class — no separate metadata file needed. The check *is* its own documentation.

### The pattern in action
Every check looks like this (you'll see all six in Week 3):
```python
class BlockingCallInAsync(Check):       # inherits the contract
    code = "CH001"                       # fills in the metadata
    name = "blocking-call-in-async"
    description = "..."
    def run(self, tree, parents, path):  # implements the required method
        findings = []
        ...
        return findings
```

It **inherits** `Check`, **overrides** the three attributes, and **implements** `run`. That's the entire pattern. Six checks, one shape.

> This is the **Strategy pattern** (each check is an interchangeable strategy for "find a bug") combined with the **Template/Interface** idea (the base class defines the slot). You don't need the jargon, but if a senior asks "what design pattern is this," that's the honest answer.

## 4. How `Finding` and `Check` fit together — the data flow

```
   scan_file(path)                          [core.py, Day 9]
        │ parses → tree, builds → parents
        ▼
   for check in checks:                      ← each check obeys the Check contract
        check.run(tree, parents, path)       ← receives the 3 inputs
                │
                ▼ produces
        [ Finding(...), Finding(...) ]        ← returns list[Finding]
        │
        ▼ collected & sorted
   the CLI calls f.as_text() / f.as_dict()   ← Finding renders itself  [Day 21]
        │
        ▼
   path:line:col: CODE message               ← the product
```

Two tiny classes — `Finding` (the output shape) and `Check` (the input/behavior shape) — are the **spine** of the entire tool. Everything in Weeks 2 and 3 plugs into them.

## 5. 🔧 Exercise — make a Finding, build a fake check

In a REPL:
```python
from codehound.core import Finding, Check
import ast

f = Finding(path="x.py", line=3, col=4, code="CH999", message="demo bug")
print(f.as_text())      # x.py:3:4: CH999 demo bug
print(f.as_dict())      # {'path': 'x.py', ...}
# try to mutate it — see frozen in action:
try:
    f.line = 9
except Exception as e:
    print("frozen!", e)

# write a 3-line check that flags every function named 'foo'
class NoFoo(Check):
    code = "CH100"; name = "no-foo"; description = "functions named foo are banned"
    def run(self, tree, parents, path):
        return [Finding(path, n.lineno, n.col_offset, self.code, f"`{n.name}` is named foo")
                for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "foo"]

tree = ast.parse("def foo():\n    pass\ndef bar():\n    pass")
print(NoFoo().run(tree, {}, "<demo>"))   # one finding, for foo
```

You just wrote a real codehound check. It obeys the contract, so it would plug straight into the engine. That's how little there is to it once you understand `Finding` and `Check`.

## ✅ Say this out loud (Day 4 mastery check)
> *"Two classes define the contract. `Finding` is an immutable, frozen dataclass holding the five fields of a result and knowing how to render itself as text or a dict. `Check` is the base class every rule inherits — it declares the `code`/`name`/`description` metadata and a `run(tree, parents, path) -> list[Finding]` method, with `NotImplementedError` forcing subclasses to implement it. Because every check obeys this shape, the engine runs them all with one loop and never needs to know which checks exist."*

Tomorrow: the cleverest helper in the engine — `build_parents`, which fixes the one big limitation of the `ast` module.
