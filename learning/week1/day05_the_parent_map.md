# Day 05 — The parent map (the cleverest 10 lines in codehound)

> This is the trick that makes codehound *work*. The `ast` module has one big limitation, and `build_parents` is the elegant fix. If you understand today, you understand the spine of every check that asks "where am I?". Open `core.py` lines 87–110.

---

## 1. The limitation: AST nodes don't know their parents

Yesterday you used `ast.walk` to go *down* the tree (parent → children). But checks constantly need to go **up**:

- CH001: "Is this `time.sleep` call inside an `async def`?" → walk *up* to find the enclosing function.
- CH005: "Is this `open()` inside a `with` block?" → walk *up* looking for a `With`.
- CH006: "Is this `create_task` awaited or assigned?" → look *up* one level at the parent.

But here's the problem — **an AST node has no `.parent` attribute.** Python's `ast` deliberately doesn't record parents. Given a `Call` node, the tree gives you its *children* (`func`, `args`) but there's no built-in way to ask "what node contains me?"

```python
import ast
call = ast.parse("async def f():\n    time.sleep(1)").body[0].body[0].value
call.parent        # AttributeError! there is no such thing
```

So how does CH001 know the call is inside an `async def`? It can't — *unless we build the parent links ourselves.* That's what `build_parents` does.

## 2. The fix: build a child → parent dictionary (lines 87–97)

```python
def build_parents(tree: ast.AST) -> dict:
    """Map id(child) -> parent_node for the whole tree."""
    parents: dict = {}
    for parent in ast.walk(tree):                 # visit every node as a potential parent
        for child in ast.iter_child_nodes(parent): # its DIRECT children
            parents[id(child)] = parent             # record: this child's parent is `parent`
    return parents
```

Read it slowly — it's only 4 real lines and it's beautiful:

1. **`for parent in ast.walk(tree)`** — walk every node in the tree. Each node is, potentially, somebody's parent.
2. **`for child in ast.iter_child_nodes(parent)`** — for that node, get its *direct* children (Day 3: `iter_child_nodes` = one level down, not the whole subtree).
3. **`parents[id(child)] = parent`** — record the link: "this child's parent is this node."

After this runs once, `parents` is a dictionary that, for any node, tells you its parent. We just gave the tree the upward links it was missing.

> Notice it pairs the two walk functions perfectly: `ast.walk` (every node) × `ast.iter_child_nodes` (direct kids of each) = every (parent, child) edge in the tree, exactly once.

## 3. The `id()` subtlety — why not use the node itself as the key?

The line is `parents[id(child)] = parent`, **not** `parents[child] = parent`. Why the `id()`?

`id(obj)` returns the unique memory address of an object — a stable integer that identifies *that exact object*. We use it as the dict key for two reasons:

1. **AST nodes aren't reliably hashable by identity the way we want.** We want "*this specific node object*," not "any node that looks equal." `id()` gives us identity-based keys: two different `Name` nodes that both say `id='x'` are *different* entries, because they're different objects at different addresses.
2. **It's cheap and exact.** `id()` is O(1) and guaranteed unique for live objects.

> ⚠️ Subtle but important: `id()` is only unique while the object is **alive**. If the tree were garbage-collected, addresses could be reused. codehound is fine because the `tree` stays alive for the whole scan (it's passed into every check), so all node `id()`s remain valid. This is exactly the kind of detail an interviewer loves — and you'd answer: *"`id()` is safe here because the tree outlives the parents map; both live for the duration of `scan_file`."*

## 4. Using the map: walking upward (lines 100–110)

Now that parents exist, going up is a simple loop. Here's `enclosing_function` (you'll study it properly Day 6, but see how it uses the map):

```python
def enclosing_function(node, parents):
    cur = node
    while cur is not None:
        p = parents.get(id(cur))       # who's my parent?
        if p is None:                  # hit the top (Module has no parent) → give up
            return None
        if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return p                   # found the enclosing function
        cur = p                        # step up one level, repeat
    return None
```

The loop: *start at the node, look up my parent, is it a function? no → become my parent and repeat.* It climbs the tree one link at a time using the map, until it finds a function or runs off the top. **This upward climb is impossible without `build_parents`.** That's why the map is built once per file (`core.py` line 190) and handed to every check.

## 5. Why build it once and pass it around?

Look at `scan_file` (core.py lines 186–193):
```python
tree = ast.parse(source, filename=path)
parents = build_parents(tree)              # built ONCE per file
for check in checks:
    findings.extend(check.run(tree, parents, path))   # shared by ALL checks
```

Building the map is O(number of nodes) — it walks the whole tree. If each of the six checks built its own, that's 6× the work per file. Instead it's built **once** and passed to every check via the contract (Day 4: `run(tree, parents, path)`). This is a deliberate performance decision: *do the expensive shared setup once, share the result.*

> ✅ **Line:** *"Python's AST nodes don't store parent pointers, but several checks need to walk upward — 'is this call inside an async function?'. So `build_parents` precomputes a child-to-parent map once per file using `id(node)` as identity keys, and the engine passes it to every check. It's built once and shared so the O(n) tree walk isn't repeated six times."*

## 6. The big picture: this is *the* enabling idea

Almost every "smart" thing codehound does — knowing scope, knowing nesting, distinguishing `await client.get()` from `requests.get()` — depends on being able to walk **up** the tree. The standard library doesn't give you that. `build_parents` is the ~10 lines that unlock it. When you explain codehound, this is the part that shows you understand the AST *deeply*, not just superficially.

## 7. 🔧 Exercise — build and use the map by hand

```python
import ast
from codehound.core import build_parents, enclosing_function

src = "async def handler():\n    time.sleep(1)\n"
tree = ast.parse(src)
parents = build_parents(tree)

# grab the time.sleep Call node
call = [n for n in ast.walk(tree) if isinstance(n, ast.Call)][0]

# climb manually:
p = parents[id(call)]
print(type(p).__name__)            # Expr (the statement wrapping the call)
print(type(parents[id(p)]).__name__)  # AsyncFunctionDef  ← we climbed two levels up!

# now let the helper do it:
fn = enclosing_function(call, parents)
print(type(fn).__name__, fn.name)  # AsyncFunctionDef handler
```

You just used the parent map to answer "what function is this call in?" — the exact question CH001 asks. Tomorrow you'll read `enclosing_function` and `is_awaited` in full.

## ✅ Say this out loud (Day 5 mastery check)
> *"Python's AST doesn't record parent links, but checks need to walk upward to answer scope questions. `build_parents` walks the tree once and, for every node, records `id(child) -> parent` in a dict — pairing `ast.walk` with `ast.iter_child_nodes` to capture every edge. It uses `id()` for identity-based keys, which is safe because the tree outlives the map. It's built once per file and shared with all six checks via the contract, so the O(n) walk isn't repeated."*

🎉 **Week 1 complete.** You now understand: what static analysis is, how code becomes an AST, the `ast` toolkit, the `Finding`/`Check` contract, and the parent-map trick. **That's the entire foundation** — Week 2 (the engine) and Week 3 (the checks) are now just "applying what you know." Next: Day 6, the AST helpers in full.
