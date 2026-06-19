# Day 02 — How Python runs your code (source → tokens → AST → bytecode)

> codehound works on the **AST**. To understand why, you need to see where the AST sits in Python's pipeline. Today you'll trace a line of code from text to execution. This is the single most important concept in the whole tool.

---

## 1. Your code is just text

When you write:

```python
async def f():
    time.sleep(1)
```

…to your computer that's literally a string of characters: `a`, `s`, `y`, `n`, `c`, space, `d`, `e`, `f`… Python can't *do* anything with raw text. It has to understand it in stages. There are **four stages**:

```
   SOURCE TEXT
       │   (1) tokenize / lex
       ▼
    TOKENS          async, def, f, (, ), :, NEWLINE, INDENT, time, ., sleep, (, 1, ) …
       │   (2) parse
       ▼
     AST            a tree of nodes  ← codehound lives HERE
       │   (3) compile
       ▼
   BYTECODE         low-level instructions for the Python VM
       │   (4) execute
       ▼
   IT RUNS
```

Let's walk each stage.

## 2. Stage 1 — Tokenizing (text → tokens)

The **tokenizer** (a.k.a. lexer) chops the character stream into meaningful chunks called **tokens** — the "words" of the language. `async` becomes one `NAME`/keyword token, `(` becomes an `OP` token, `1` becomes a `NUMBER` token, indentation becomes `INDENT`/`DEDENT` tokens.

It's purely mechanical — it doesn't understand *meaning*, just *boundaries*. `time.sleep` becomes three tokens: `time`, `.`, `sleep`. The tokenizer doesn't know `time` is a module; it just knows it's a name.

> Analogy: tokenizing is reading a sentence and identifying each *word* and *punctuation mark*, without yet understanding grammar.

You can see it yourself:
```bash
python -c "import tokenize, io; [print(t) for t in tokenize.generate_tokens(io.StringIO('time.sleep(1)').readline)]"
```

## 3. Stage 2 — Parsing (tokens → AST) ← **this is where codehound works**

The **parser** takes the flat stream of tokens and builds a **tree** that captures the *grammatical structure* — what's nested inside what. This tree is the **AST: Abstract Syntax Tree**.

- **Tree** because code is hierarchical: a function *contains* statements, a statement *contains* an expression, a call *contains* arguments.
- **Syntax** because it represents the grammar/structure of the code.
- **Abstract** because it throws away noise that doesn't affect meaning — whitespace, comments, the exact parentheses. `(1)` and `1` become the same node; `time.sleep( 1 )` and `time.sleep(1)` produce identical trees.

Our example becomes (simplified):

```
Module
└── AsyncFunctionDef  name='f'
    └── body:
        └── Expr
            └── Call
                ├── func: Attribute  attr='sleep'
                │         └── value: Name  id='time'
                └── args: [ Constant value=1 ]
```

Read that tree top-down: *a module containing an async function named `f`, whose body is one expression: a call, whose function is the attribute `sleep` on the name `time`, with one argument, the constant `1`.*

**This is the representation codehound reasons about.** When CH001 asks "is there a blocking call inside an async function?", it's really asking: *"is there a `Call` node to `time.sleep`, whose nearest enclosing `...FunctionDef` ancestor is an `AsyncFunctionDef`?"* — a question about **tree shape**.

> Analogy: parsing is taking the words of a sentence and diagramming the grammar — subject, verb, object, and which clauses are nested inside which.

## 4. Stages 3 & 4 — Compile & execute (codehound never goes here)

After the AST, Python **compiles** the tree into **bytecode** (compact instructions like `LOAD_NAME`, `CALL_FUNCTION`) and the **interpreter executes** them. This is where code actually *runs* — files open, network calls fire, `time.sleep` actually sleeps.

**codehound stops after Stage 2.** It builds the AST and inspects it, then throws it away. It never compiles, never executes. That's the whole meaning of "static" — we analyze the *structure*, never the *behavior*. This is why codehound can analyze code whose dependencies aren't installed, code that would crash if run, even code for a different OS.

## 5. Why the AST and not the other stages?

Could codehound work on tokens, or on text directly (regex)? People try. Here's why the AST is the right altitude:

- **Text/regex is too low.** A regex for `time.sleep` would match it inside a comment, inside a string `"time.sleep"`, or in a variable named `downtime_sleep`. It has no concept of "inside a function." Fragile and false-positive-prone.
- **Tokens are too flat.** Tokens know `time . sleep ( 1 )` are adjacent, but not that they form a *call*, nor what *contains* that call. You can't ask "what function is this in?" from a flat token list.
- **Bytecode is too late & too lossy.** By bytecode, `time.sleep` and `await asyncio.sleep` look structurally similar and you've lost the clean "this is inside an `async def`" signal. Also you'd have to compile (and thus need imports).

The AST is the **sweet spot**: high enough to know structure and nesting, low enough to be exact about what the code literally says.

> ✅ **Interview-worthy line:** *"I work at the AST level because it's the right altitude — regex on text can't tell code from a comment or know what scope you're in, and bytecode is too late and requires compiling. The AST gives you exact, structural facts: this is a Call node, to this attribute, inside this async function."*

## 6. The key mental model for the rest of the course

Burn this in: **every check in codehound is a question about the shape of the AST tree.**

- CH001: "Is there a `Call` to a blocking function whose enclosing function is `AsyncFunctionDef`?"
- CH002: "Does a `FunctionDef` have a default argument that is a `List`/`Dict`/`Set` node?"
- CH006: "Is there a bare `Expr` statement that is a `Call` to `create_task`?"

Once you see checks as *tree-shape questions*, the code in Week 3 reads like English.

## 7. 🔧 Exercise — see the tree yourself

Run this and stare at the output:

```bash
python -c "import ast; print(ast.dump(ast.parse('async def f():\n    time.sleep(1)'), indent=4))"
```

You'll see `AsyncFunctionDef`, `Expr`, `Call`, `Attribute(attr='sleep')`, `Name(id='time')`, `Constant(value=1)` — the exact node types codehound checks for. Now change `time.sleep(1)` to `await asyncio.sleep(1)` and re-run. Notice the new `Await` node wrapping the `Call`. **That `Await` wrapper is exactly what CH001 looks for to know "this is safe, skip it"** (you'll see `is_awaited` on Day 6).

## ✅ Say this out loud (Day 2 mastery check)
> *"Python runs code in four stages: tokenize the text into words, parse the tokens into an Abstract Syntax Tree, compile the tree to bytecode, then execute. codehound only goes as far as the AST — it reads the tree's structure and never runs the code. The AST is the right level because it knows nesting and scope, unlike regex or tokens, without needing to compile or run anything."*

Tomorrow: **get hands-on with the `ast` module** — the actual nodes, `ast.walk`, and how to read any tree.
