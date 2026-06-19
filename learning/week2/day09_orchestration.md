# Day 09 — Orchestration: `scan_file` & `scan_path`

> These two functions are the conductor — they tie discovery, parsing, the parent map, and the checks together into one flow. Open `core.py` lines 180–206.

---

## 1. `scan_file` (lines 180–194)
```python
def scan_file(path, checks):
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return []
    parents = build_parents(tree)
    findings = []
    for check in checks:
        findings.extend(check.run(tree, parents, path))
    return findings
```
Five steps for one file: **read → parse → build parents → run every check → collect**. Note the two `try/except` guards:
- **`(OSError, UnicodeDecodeError)`** — an unreadable file (permissions, binary, weird encoding) returns `[]` instead of crashing the whole run.
- **`SyntaxError`** — codehound parses with the *current* Python's grammar. A file using newer syntax (or Python 2) can't be parsed; we skip it gracefully rather than abort.

This **resilience** is essential: scanning a 6-million-line repo, you *will* hit one weird file. One bad file must not kill the scan.

## 2. The central loop (the contract paying off)
```python
for check in checks:
    findings.extend(check.run(tree, parents, path))
```
This is the moment the Day-4 contract pays off. The loop doesn't know what any check *does* — it just hands each the same three inputs and collects `list[Finding]`. Add a seventh check and this line never changes.

## 3. `scan_path` (lines 197–206)
```python
def scan_path(root, checks, skip_dirs=DEFAULT_SKIP_DIRS):
    findings = []
    for path in iter_python_files(root, skip_dirs):
        findings.extend(scan_file(path, checks))
    findings.sort(key=lambda f: (f.path, f.line, f.col, f.code))
    return findings
```
The top-level driver: discover files → scan each → **sort deterministically** by `(path, line, col, code)`.

**Why sort?** So the same input always produces the same output order. That makes the output **diffable** (compare two runs), **testable** (assert exact order), and **readable** (grouped by file, top-to-bottom). Non-deterministic output is a subtle bug in any tool that feeds CI.

## 4. 🔧 Exercise
```python
from codehound.checks import get_checks
from codehound.core import scan_path
for f in scan_path("src", get_checks()):
    print(f.as_text())     # codehound scanning itself — sorted, clean
```
Then point it at one of your cloned target repos and watch findings stream out.

## 5. 💬 Interview Q&A
**Q: What happens if one file in a huge repo has a syntax error or bad encoding?**
A: `scan_file` catches `SyntaxError` and `(OSError, UnicodeDecodeError)` and returns `[]` for that file, so the scan continues. One bad file never aborts the run.

**Q: Why parse with `ast.parse` per file instead of once?**
A: Each file is an independent module with its own tree; there's no shared global tree. Per-file parsing also bounds memory and lets us skip unparseable files individually.

**Q: Why sort the findings?**
A: Determinism — diffable, testable, readable output. CI and tests rely on stable ordering.

**Q: Where is the parent map built, and how often?**
A: Once per file in `scan_file`, right after parsing — so all checks on that file reuse the same map.

**Q: Is this parallelizable?**
A: Yes — files are independent, so `scan_file` could run in a process pool, then merge-and-sort. It's single-threaded today for simplicity; that'd be a natural optimization.

## ✅ Say this out loud
> *"`scan_file` reads a file, parses it to an AST, builds the parent map, and runs every check via the shared contract, guarding against unreadable or unparseable files so one bad file can't kill the scan. `scan_path` drives that over every discovered file and sorts the findings by path/line/col/code for deterministic, diffable output. Because files are independent, it's embarrassingly parallel if I ever need speed."*

Tomorrow: the package surface — what `__init__.py` and `__all__` actually promise.
