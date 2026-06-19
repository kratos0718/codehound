# Day 03 — The `ast` module, hands-on

> Yesterday you saw *that* code becomes a tree. Today you learn the actual Python tools to **build, walk, and read** that tree — `ast.parse`, `ast.walk`, `ast.dump`, and node attributes. These five functions are 90% of how codehound works. Keep a Python REPL open and run everything.

---

## 1. `ast.parse` — text in, tree out

The entry point. Give it source code (a string), get back the root node of the AST:

```python
import ast
tree = ast.parse("x = 1 + 2")
print(tree)          # <ast.Module object at 0x...>
```

`ast.parse` *is* "Stage 2" from yesterday, exposed as a function. The root is always a `Module` node. In codehound this happens in exactly one place — `core.py`:

```python
tree = ast.parse(source, filename=path)   # core.py line 187
```

The `filename=path` argument doesn't change the tree; it just makes error messages say *which* file failed to parse. (More on that Day 9.)

## 2. Every node is an object with **fields**

Each node is an instance of an `ast.<Something>` class, and its children are stored in named attributes called **fields**. Example:

```python
tree = ast.parse("time.sleep(1)")
call = tree.body[0].value          # dig down to the Call node
print(type(call))                  # <class 'ast.Call'>
print(call.func)                   # <ast.Attribute ...>
print(call.func.attr)              # 'sleep'      ← the attribute name
print(call.func.value.id)          # 'time'       ← the object it's called on
print(call.args)                   # [<ast.Constant ...>]
print(call.args[0].value)          # 1
```

Notice the pattern: `Call` has fields `func` and `args`; `Attribute` has fields `value` and `attr`; `Name` has field `id`. **codehound is mostly just reaching into these fields** — e.g. CH001 reads `func.attr` ("sleep") and `func.value.id` ("time") to decide if a call is blocking. You saw that exact code yesterday; now you know what `.attr` and `.id` *are*.

### The node types you'll meet constantly
| Node | What it is | Key fields |
|------|-----------|-----------|
| `Module` | the whole file (the root) | `body` (list of statements) |
| `FunctionDef` / `AsyncFunctionDef` | `def` / `async def` | `name`, `args`, `body` |
| `Call` | a function call `f(...)` | `func`, `args`, `keywords` |
| `Attribute` | dotted access `a.b` | `value` (the `a`), `attr` (the `"b"`) |
| `Name` | a bare identifier `x` | `id` (the `"x"`) |
| `Constant` | a literal `1`, `"hi"`, `None` | `value` |
| `Expr` | a statement that's just an expression | `value` (the expression) |
| `Assign` | `x = ...` | `targets`, `value` |
| `Await` | `await something` | `value` |
| `With` / `AsyncWith` | a `with` block | `items`, `body` |

You do **not** need to memorize these — you'll meet each one in context. Bookmark this table.

## 3. `ast.dump` — print the whole tree

Your best friend for understanding any code. It renders the entire tree as text:

```python
print(ast.dump(ast.parse("def f(x=[]): return x"), indent=4))
```
```
Module(body=[
    FunctionDef(
        name='f',
        args=arguments(
            args=[arg(arg='x')],
            defaults=[List(elts=[], ...)]),   ← the mutable default CH002 hunts!
        body=[Return(value=Name(id='x'))])])
```

When you're confused about what shape some code produces, `ast.dump` it. This is literally how you'd *design* a new check (Day 24): write the bad code, dump it, see the node shape, then write code that matches that shape.

## 4. `ast.walk` — visit every node

A check needs to look at *all* nodes, not just the top. `ast.walk(tree)` yields **every node in the tree**, in no particular guaranteed order (breadth-ish), flat:

```python
tree = ast.parse("async def f():\n    time.sleep(1)")
for node in ast.walk(tree):
    print(type(node).__name__)
# Module, AsyncFunctionDef, Expr, Call, Attribute, arguments, Name, Load, Constant
```

**This is the backbone of every check.** Look at any `checks/*.py` and you'll see:

```python
for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue
    ...
```

The idiom is always: *walk every node → skip the ones that aren't the type I care about → inspect the rest.* The `isinstance(node, ast.Call)` guard is how a check says "I only care about function calls."

> `ast.walk` is "give me every node, flat." It's perfect for "find all calls anywhere." Its weakness: it loses the *position* of a node in the tree — it doesn't tell you a node's parent. That limitation is the entire reason `build_parents` exists (Day 5).

## 5. `ast.iter_child_nodes` — visit only the **direct** children

Where `ast.walk` goes all the way down, `ast.iter_child_nodes(node)` yields only the *immediate* children of one node (one level down):

```python
mod = ast.parse("a = 1\nb = 2")
list(ast.iter_child_nodes(mod))    # [<Assign a=1>, <Assign b=2>]  ← just the two statements
```

codehound uses this in exactly one place — building the parent map (Day 5) — because to record "child → parent" links you need to know, for each node, which nodes are *directly* under it.

## 6. `lineno` and `col_offset` — where a node lives

Every node that corresponds to real source has two crucial attributes:
- `node.lineno` — the 1-based line number
- `node.col_offset` — the 0-based column

```python
call = ast.parse("x = 1\ntime.sleep(1)").body[1].value
print(call.lineno, call.col_offset)   # 2 0
```

This is how a `Finding` knows *where* to point the developer. Every check ends by constructing a `Finding(line=node.lineno, col=node.col_offset, ...)`. Without these, codehound could say "there's a bug" but not *where* — useless. (Note CH002 reports `default.lineno`, the position of the *default value* specifically, not the whole function — precision matters.)

## 7. The complete mental loop

Putting today together, **every check is this shape**:

```python
for node in ast.walk(tree):          # 1. visit every node
    if not isinstance(node, X):      # 2. filter to the type I care about
        continue
    if <fields don't match bug>:     # 3. read .attr/.id/.value etc.
        continue
    findings.append(Finding(         # 4. record location + message
        line=node.lineno, col=node.col_offset, ...))
```

Once you internalize this skeleton, Week 3 is just "what goes in the blanks for each bug."

## 8. 🔧 Exercise — read a tree by hand

In a REPL:
```python
import ast
src = "async def handler():\n    with open('x') as f:\n        data = requests.get(url)\n"
print(ast.dump(ast.parse(src), indent=4))
```
Now answer *from the dump alone* (then verify):
1. What node type is `handler`? (Answer: `AsyncFunctionDef`)
2. Is the `requests.get(url)` `Call` inside a `With`? (trace the nesting)
3. What is `call.func.attr` and `call.func.value.id` for that call? (`'get'`, `'requests'`)

You just did, by hand, what CH001 does automatically. That's the whole magic trick.

## ✅ Say this out loud (Day 3 mastery check)
> *"The `ast` module is how I work with the tree: `ast.parse` turns source into nodes, each node is an object with named fields like `Call.func` or `Attribute.attr`, `ast.walk` yields every node so a check can filter to the type it cares about with `isinstance`, and every node carries `lineno`/`col_offset` so a finding can point at the exact spot. `ast.dump` lets me see any tree's shape, which is how I design a new check."*

Tomorrow: the **`Finding` dataclass and `Check` base class** — the contract that ties the engine and the checks together.
