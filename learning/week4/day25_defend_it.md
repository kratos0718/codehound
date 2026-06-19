# Day 25 — Defend it: the interview script & tradeoffs

> The finale. Today isn't new material — it's *assembly*. By the end you can walk anyone through codehound with confidence, from a 30-second pitch to a deep architecture grilling, and handle the hard "why" questions without flinching.

---

## 1. The layered pitch (pick depth to match the room)

**10 seconds:**
> "codehound is a zero-dependency Python static analyzer I built. It finds real async and correctness bugs — and the bugs it found are merged into unsloth and agno."

**30 seconds:**
> "It parses each file into an AST, precomputes a parent map so checks can ask 'what function am I in?', and runs six independent check classes — each one distilled from a real bug I'd already fixed and gotten merged into a major AI framework. Things like a `time.sleep` freezing an async event loop, or a fire-and-forget task that gets garbage-collected mid-run. It's precision-first, runs in CI via exit codes, and has zero runtime dependencies."

**2 minutes:** add the pipeline (discover → parse → parent map → checks → sort → render), the precision-over-recall philosophy with examples (await-guard, file-handle escape hatches), the validation (merged PRs as ground truth), and the honest limitation (name-based matching; CH004's runtime blind spot).

## 2. The architecture walk (when they say "show me how it works")
1. **Entry:** `cli.py scan` → `get_checks` → `scan_path`.
2. **Discovery:** `iter_python_files` (generator, skip-dirs via `dirnames[:]`).
3. **Per file:** `scan_file` → `ast.parse` → `build_parents` (the key helper — AST has no parent pointers).
4. **Contract:** each `Check.run(tree, parents, path) → list[Finding]`; the engine loops blindly.
5. **Checks:** all six share the walk→filter→guard→emit skeleton.
6. **Output:** sort for determinism → `as_text`/`as_dict` → exit codes for CI.

Draw it as a pipeline on the whiteboard. The interviewer wants to see you *navigate your own code*, not recite it.

## 3. The tradeoffs table (have an answer ready for each)
| Decision | Why | The cost (own it) |
|----------|-----|-------------------|
| AST over regex | context-sensitivity (sync vs async, awaited) | more code than a grep |
| Name-based matching | ~50 lines, catches idiomatic usage | misses aliased imports (`import requests as r`) |
| Precision over recall | output drives PRs; false positives burn credibility | real false negatives |
| Zero dependencies | auditable, no supply-chain risk | reimplement small helpers |
| Intraprocedural | simple, reliable per-function | can't follow cross-function flows (CH005) |
| Skip tests/examples | they hold intentional bad patterns | could miss real bugs there (`--include-tests`) |

Every cost is a *deliberate* choice, not an oversight — that framing is everything.

## 4. The hard questions (and your honest answers)
- **"Isn't this just Ruff/flake8?"** → "Several checks overlap with Ruff (B006, RUF006) — deliberately, as a correctness baseline. The point isn't to replace Ruff; it's that I built the analysis engine myself to understand AST tooling, and I added async-safety checks tuned from bugs I personally fixed and got merged. Plus the empirical paper across 29 frameworks."
- **"What's the weakest part?"** → CH004's runtime blind spot (a maintainer rejected one PR) and name-based matching. Name them first; it disarms the question.
- **"How do you know it works?"** → "Maintainers merged the fixes. That's ground truth — it's literally the validation method in my paper."
- **"How would you scale it to a million files?"** → "Files are independent, so `scan_file` parallelizes across processes trivially; then merge-and-sort. Today it's single-threaded for simplicity."
- **"What would you build next?"** → "Auto-fix (codemod) suggestions, a config file for per-project check selection, and a cross-function pass for CH005."

## 5. The story arc (lead with this — it's your edge)
> "I didn't build a linter and hope. I was fixing real bugs by hand in AI frameworks, noticed they were the *same classes* of mistake over and over, so I encoded each class as a check. Then I ran the tool back at the ecosystem and it found more of the same — now under review at vLLM, Microsoft, and OpenAI. I wrote it up as an empirical study of 1,377 defects across 29 frameworks. The whole thing is ~750 lines I can explain end to end."

That arc — **fix → notice the pattern → automate → it finds more → measure it** — is a *builder's* story. Most candidates have "I used a tool." You have "I built the tool, and the industry merged what it found."

## 6. 🔧 Final exercise — the mock
Out loud, without notes, in order:
1. Give the 30-second pitch.
2. Whiteboard the pipeline (6 boxes).
3. Explain CH001 *and* its false-positive guard.
4. State one tradeoff and its cost.
5. Tell the rejection story.
6. Answer "how do you know it works?"
If you can do all six cold, you're done. You don't *remember* codehound anymore — you *understand* it.

## 7. 💬 The five questions you WILL get (one-line answers)
1. **What is it?** Zero-dep AST static analyzer for Python; finds async/correctness bugs; merged into unsloth & agno.
2. **Why AST not regex?** Context — sync vs async, awaited vs not; a grep can't see that.
3. **How do you avoid false positives?** Precision-first guards (await-skip, file-handle escape hatches, skip tests) + negative tests.
4. **How do you know it works?** Maintainers merged the fixes — ground truth, and the paper's validation method.
5. **What's its weakness?** Name-based matching + CH004's runtime blind spot — known and documented.

## ✅ The one paragraph (you now *understand* every clause)
> *"codehound is a zero-dependency Python static analyzer I built. It parses each file into an AST with the standard-library `ast` module, precomputes a child→parent map so checks can walk upward to ask 'what function is this call in?', and runs six independent Check classes that each detect one real bug class — blocking calls in async, fire-and-forget tasks, mutable defaults, unclosed files, and two deprecated-API patterns. Each check is distilled from a bug I actually found and got merged into a major AI framework. It's precision-first, outputs text/JSON/CSV with CI-friendly exit codes, and I validated it across 29 frameworks in an empirical paper."*

🎓 **You finished the 25-day path.** You can now open codehound, explain every line, justify every decision, extend it, and defend it cold. It's yours.
