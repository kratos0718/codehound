# codehound from scratch — for when you've forgotten what "AST" even means

> Read this when you're nervous before an interview. It assumes you know *nothing*. By the end you'll be able to explain codehound as a simple story. No jargon until it's earned.

---

## Part 1 — The problem that makes codehound exist

The big AI projects you contributed to — unsloth, agno — are **millions of lines of code**. Somewhere buried in there is a tiny mistake that freezes the whole server.

How do you find *that one kind of mistake* across millions of lines? You can't read it all. So you build a **robot that reads code for you** and shouts "found one!" every time it sees that mistake.

**That robot is codehound.** The whole tool is "a robot that reads code and finds a specific kind of bug."

---

## Part 2 — But how does a robot "read" code?

Two ways. One dumb, one smart.

**The dumb way — text search.** Like Ctrl+F for `time.sleep`. It's blind. It can't tell a real `time.sleep` causing a bug from the same words sitting in a comment, or a `sleep` in a *safe* place vs a *dangerous* one. Tons of false alarms. Useless.

**The smart way — understand the structure.** This is what codehound does.

---

## Part 3 — The trick: sentences become trees

English sentence:
> "The cat sat on the mat."

Your English teacher could **diagram** it: *cat* = subject, *sat* = verb, *mat* = object. She sees the **structure**, not just words in a row. Drawn out, it's a **tree**:

```
            Sentence
          /    |     \
     subject  verb   place
       cat    sat   "on the mat"
```

**Code is just a stricter language.** The line `x = sleep(5)` also has structure:

```
        Assignment
        /         \
    target        value
      x         a CALL to "sleep"
                     |
                 argument: 5
```

The computer doesn't see "x equals sleep five" as text. It sees: *this is an assignment; its value is a function call; the function is sleep; one argument.* Structure, not words.

---

## Part 4 — What "a tree" means

One thing at the top that branches into smaller things, which branch into smaller things. You already know trees:
- **A family tree** — grandparent → parents → kids.
- **Folders on your laptop** — one folder holding folders holding files.

One top, branching down to the tiny pieces at the bottom (the "leaves").

---

## Part 5 — Now the scary word is easy: AST

**AST = Abstract Syntax Tree.** Decode it backwards:
- **Tree** → the branching shape above.
- **Syntax** → fancy word for "grammar / structure."
- **Abstract** → it throws away cosmetic junk (spaces, comments) and keeps only the *meaning*.

So **AST = "your code redrawn as a structured tree of its meaning."**

Best part: you don't build the tree. Python has a built-in tool (`ast.parse`) that takes code as text and hands back the tree automatically. codehound just *uses* it.

> Resume phrase **"AST-based static analyzer"** = *"a tool that finds bugs by reading code as a meaning-tree instead of plain text."* ("Static" = it reads code *without running it*, like proofreading an essay without acting it out.)

---

## Part 6 — "Analyzer" = the part that hunts

Once code is a tree, an **analyzer** walks the tree node by node, asks yes/no questions about each, and flags the bad ones.

Like **airport security**: passengers pass one at a time, the officer checks each, pulls aside the ones that fail. codehound = the officer; tree nodes = passengers; the checks = the questions.

---

## Part 7 — The full workflow, as a story

When you run it:

1. **You type:** `codehound scan myproject/`
2. **It gathers suspects.** Finds every `.py` file, skipping junk folders (`node_modules`, `tests`).
3. **It turns each file into a tree.** `ast.parse(code)` → meaning-tree.
4. **It draws a "who's my boss?" map.** So any node can look *upward* and ask "what function am I inside?"
5. **It walks every node**, running **6 little detectives** (the checks), each trained on one bug.
6. **A detective in action (CH001, the famous one):**
   - *"Are you a `sleep` call?"* No → ignore. Yes → continue.
   - *"Are you being `await`ed (the safe way)?"* Yes → ignore. No → continue.
   - *"Look upward — am I inside an `async` function?"* No → fine. **Yes → GOTCHA** (this freezes the server).
   - Writes it down: file, line, message.
7. **It prints the report:**
   ```
   server.py:412:8: CH001 time.sleep() blocks the event loop inside async function load_checkpoint
   ```
   That one line is *exactly* the unsloth bug you got merged. 🎯

The whole machine: files → trees → walk each node → 6 detectives ask questions → write down the gotchas → print the list.

---

## Part 8 — YOUR story (the arc to tell)

> "I kept running into the same kinds of bugs by hand while contributing to AI projects — like a `sleep` freezing an async server. Instead of hunting them one at a time forever, I taught a robot to recognize the pattern. Then I pointed it at the most popular AI projects on GitHub — and it found *real* bugs. I sent the fixes, and maintainers at unsloth and agno merged them. So it's not 'I sent some PRs' — it's 'I built a tool that finds a whole class of bug, and the industry merged what it found.'"

Three beats: **I noticed a pattern → I automated finding it → it found real bugs in real software.**

---

## Part 9 — The 20-second version to memorize

> "codehound is a tool I built that finds bugs in Python code. Instead of searching the code as text, it reads it as a *structure tree* — the way an English teacher diagrams a sentence — so it can ask precise questions like 'is this slow call inside an async function?' It has six bug-detectors, each from a real bug I fixed, and the bugs it found are merged into unsloth and agno."

---

**Next step when you're ready:** open `CODE_WALKTHROUGH_A_TO_Z.md` in this same folder — it's the line-by-line version, and it'll make sense now that you have the story.
