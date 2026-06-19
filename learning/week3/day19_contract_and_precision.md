# Day 19 — The shared contract & false-positive philosophy

> No new file. Today you connect all six checks into one mental model and learn the single design principle that governs the whole tool: **precision over recall.**

---

## 1. The shared shape
Re-read the six checks back to back and you'll see they're the *same skeleton*:
```python
class Xxx(Check):
    code = "CH00n"; name = "..."; description = "..."
    def run(self, tree, parents, path):
        findings = []
        for node in ast.walk(tree):
            if <not the node type I care about>: continue
            if <fails my specific conditions>: continue
            if <matches a false-positive guard>: continue
            findings.append(Finding(path, node.lineno, node.col_offset, self.code, msg))
        return findings
```
Walk → filter by node type → apply precise conditions → apply guards → emit. Once you've seen one, you've seen all six. *That's the power of the contract* (Day 4): uniform shape, independent logic.

## 2. Precision vs. recall (the core tradeoff)
Two ways a checker can be wrong:
- **False positive** — flags correct code (cries wolf).
- **False negative** — misses a real bug (stays silent).

**Recall** = "of all real bugs, how many did I catch?" **Precision** = "of everything I flagged, how much was actually a bug?"

codehound is deliberately **precision-first**. Why? Because of *how it's used*: I take its output and open PRs to maintainers. **One false positive wastes a maintainer's time and burns my credibility.** A missed bug costs nothing visible. So every check would rather stay silent than cry wolf.

## 3. Where you can see the philosophy in the code
- **CH001** skips `await`ed calls and sync functions.
- **CH005** skips returned handles, explicit `.close()`, and `with` blocks.
- **CH006** skips assigned/awaited/returned tasks and `TaskGroup`.
- **Engine** skips `tests/`, `examples/`, `docs/` (fixtures full of intentional "bad" code).
- **Matching** is conservative and name-based — it would rather miss `import requests as r` than guess wrong.

Every one of those is a **recall sacrifice for precision**.

## 4. The flip side — honest about misses
Precision-first means real false negatives, and you should name them confidently:
- Aliased imports (`r.get()`).
- Attribute-target file handles (`self.fh = open(...)`).
- Cross-function flows (a handle closed by a helper).
- CH004's runtime-context blindness.

Naming your tool's blind spots is a *strength* signal in interviews — it shows you understand the limits of static analysis, not just the happy path.

## 5. 💬 Interview Q&A
**Q: What's the design principle behind codehound?**
A: Precision over recall. Its output drives PRs to real maintainers, so a false positive is expensive (wasted time, lost credibility) while a miss is cheap. Every check is built to stay silent when unsure.

**Q: Define precision and recall in this context.**
A: Precision = fraction of my flags that are real bugs. Recall = fraction of real bugs I catch. I optimize precision, accepting lower recall.

**Q: Give three concrete examples of precision-over-recall in the code.**
A: CH001 skipping awaited calls; CH005's three escape hatches; skipping tests/examples dirs. All trade catching-more for flagging-wrong-less.

**Q: Isn't missing bugs bad?**
A: It's the right call *for this use case*. If codehound were a CI gate on my own repo, I might tune for higher recall. The optimum depends on the cost of each error type.

**Q: How do you know your precision is good?**
A: The empirical evidence: maintainers merged the fixes. Merged PRs are ground-truth confirmation that the flags were real — that's the validation method in my paper.

## ✅ Say this out loud
> *"All six checks share one shape — walk the tree, filter by node type, apply precise conditions, apply false-positive guards, emit a Finding. The governing principle is precision over recall: because the output becomes PRs to maintainers, a false positive costs credibility while a miss costs nothing visible, so each check stays silent when unsure. I can name the resulting blind spots — aliased imports, attribute targets, cross-function flows — and the validation that it works is that maintainers merged the fixes."*

Tomorrow: the receipts — mapping each check to the real merged PR it produced.
