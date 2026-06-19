# Day 22 — Testing: positive *and* negative cases

> Tests are where you *prove* a checker is trustworthy. The signature of a good static-analysis test suite is that it tests what *shouldn't* fire as hard as what should. Open `tests/test_checks.py`.

---

## 1. The test harness (lines 15–21)
```python
def _run(code: str, select: list[str]) -> list:
    tree = ast.parse(code)
    parents = build_parents(tree)
    findings = []
    for check in get_checks(select):
        findings.extend(check.run(tree, parents, "<test>"))
    return findings
```
Each test passes a tiny **inline source snippet** and the check(s) to run, and gets back findings. No files, no fixtures on disk — the snippet *is* the test case. Fast and self-documenting.

## 2. The pattern: every check has positives AND negatives
For each check there are two kinds of test:
- **Positive** — the bad pattern *is* flagged (`len(findings) == 1`).
- **Negative** — a *correct* version is *not* flagged (`== []`).

Example, CH005:
```python
def test_ch005_flags_unclosed_open():     # positive
    assert len(_run("def f(p):\n fh=open(p)\n return fh.read()\n", ["CH005"])) == 1
def test_ch005_ignores_with_open():       # negative
    assert _run("def f(p):\n with open(p) as fh:\n  return fh.read()\n", ["CH005"]) == []
def test_ch005_ignores_explicit_close():  # negative
def test_ch005_ignores_returned_handle(): # negative
```
**Three of CH005's four tests are negatives** — they pin down the false-positive guards. That ratio is the point: a checker that flags everything is easy; a checker that flags *only* real bugs needs the negatives to prove it.

## 3. The negatives are your guards, frozen in place
Map each negative test to the guard it protects:
- `test_ch001_ignores_sleep_in_sync_function` → the async-only rule.
- `test_ch001_ignores_awaited_call_on_sync_named_receiver` → `is_awaited` (the AutoGPT false positive).
- `test_ch001_ignores_await_asyncio_sleep` → awaited calls.
- `test_ch005_ignores_returned_handle` → the `returns_handle` escape hatch.
- `test_ch006_ignores_taskgroup_create_task` → the TaskGroup exclusion.

If someone later "improves" a check and breaks a guard, the negative test goes red. **The negatives are regression insurance for precision.**

## 4. Why inline snippets (not fixture files)?
The bug and the assertion sit in the same five lines — you read the test and instantly see what it's about. Fixture files force you to jump around. For a rule-based tool, tiny inline cases are the sweet spot.

## 5. 🔧 Exercise
```bash
pip install -e ".[dev]"   # gets pytest
pytest -q                 # all green
```
Then **break a guard on purpose**: in `blocking_async.py`, delete the `is_awaited` skip and run `pytest -q`. Watch `test_ch001_ignores_await_asyncio_sleep` fail. Revert. You just felt the safety net catch.

## 6. 💬 Interview Q&A
**Q: How do you test a static analyzer?**
A: Inline source snippets through a small harness that parses, builds parents, and runs the check. Crucially, every check has both positive tests (bad code is flagged) and negative tests (correct code is *not*).

**Q: Why so many negative tests?**
A: They encode the false-positive guards. For a precision-first tool, proving what *doesn't* fire is as important as what does — the negatives are regression insurance against someone breaking a guard later.

**Q: Give an example of a negative test catching a real issue.**
A: `test_ch001_ignores_awaited_call_on_sync_named_receiver` — modeled on a real AutoGPT false positive where an async client was named `requests`. If the `is_awaited` guard regresses, that test fails.

**Q: Why inline snippets over fixture files?**
A: The code-under-test and the assertion are co-located and tiny, so each test is self-documenting and fast.

## ✅ Say this out loud
> *"Tests run tiny inline snippets through a harness that parses, builds the parent map, and runs the check. Every check has positives (bad code flagged) and negatives (correct code not flagged), and the negatives outnumber positives for the tricky checks because they pin the false-positive guards — like the awaited-call and TaskGroup cases drawn from real false positives. They're regression insurance: break a guard and a negative test goes red."*

Tomorrow: packaging & CI — how it installs, ships, and tests itself across Python versions.
