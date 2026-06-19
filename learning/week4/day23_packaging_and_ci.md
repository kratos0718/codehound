# Day 23 — Packaging & CI: `pyproject.toml` and the GitHub workflow

> How codehound becomes an installable tool (`pip install`, a `codehound` command) and how it proves itself on every push. Open `pyproject.toml` and `.github/workflows/ci.yml`.

---

## 1. `pyproject.toml` — the package manifest
The modern, standard packaging file (PEP 621). Key parts:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "codehound"
version = "0.1.0"
requires-python = ">=3.9"
dependencies = []                       # ← ZERO runtime deps
keywords = ["static-analysis","linter","ast","asyncio","bug-finder"]

[project.scripts]
codehound = "codehound.cli:main"        # ← creates the `codehound` command

[project.optional-dependencies]
dev = ["pytest>=7"]                     # ← only needed to develop/test
```
Three things to call out:
- **`dependencies = []`** — zero runtime dependencies. The whole tool runs on the standard library (`ast`, `os`, `argparse`, `json`). This is a *feature*: nothing to break, instant install, auditable in one sitting.
- **`[project.scripts]`** — maps the name `codehound` to `codehound.cli:main`, so after install you can type `codehound scan ...` directly (no `python -m`).
- **`requires-python = ">=3.9"`** — the floor; the AST node types it uses exist from 3.9.

The `[tool.hatch.build...]` and `[tool.pytest...]` sections tell the build backend where the package lives (`src/codehound`) and pytest where tests live.

## 2. `ci.yml` — continuous integration
```yaml
strategy:
  matrix:
    python-version: ["3.9", "3.11", "3.12"]
steps:
  - install: pip install -e ".[dev]"
  - run tests: pytest -q
  - self-scan: codehound scan src --exit-zero
```
Two jobs on every push/PR:
1. **Test matrix** — runs the full pytest suite on **Python 3.9, 3.11, and 3.12**. AST node shapes shift slightly across versions; the matrix proves codehound parses and runs correctly on all three.
2. **The self-scan (the cool part)** — `codehound scan src --exit-zero` runs codehound **on its own source code**. It's *dogfooding*: the tool that finds bugs is held to its own standard. `--exit-zero` means the scan reports but doesn't fail the build (a finding in its own code shouldn't block a docs PR), but it's there and visible.

## 3. Why "zero dependencies" is a real selling point
Say it plainly in interviews: *"It has no third-party runtime dependencies — it's built entirely on Python's standard library."* That means: no supply-chain risk, no version-conflict hell for users, trivial to install, and a reviewer can audit the *entire* tool without learning a framework. For a security/quality tool, that minimalism is credibility.

> Note: there's a `.ruff_cache` in the repo — `ruff` was used as a linter/formatter during development. It isn't a runtime dependency (not in `dependencies`), and CI runs pytest + the self-scan rather than ruff.

## 4. 🔧 Exercise
```bash
pip install -e .
codehound --version          # codehound 0.1.0  (the [project.scripts] entry works)
codehound scan src --exit-zero
```

## 5. 💬 Interview Q&A
**Q: How is codehound packaged and installed?**
A: A PEP 621 `pyproject.toml` with hatchling. `pip install` it and a `[project.scripts]` entry point exposes a `codehound` command mapped to `cli:main`.

**Q: What are its dependencies?**
A: None at runtime — `dependencies = []`. It's pure standard library (`ast`, `os`, `argparse`, `json`). Pytest is the only dev dependency.

**Q: Why is zero-dependency a deliberate choice?**
A: No supply-chain risk, trivial install, no version conflicts for users, and the whole tool is auditable. For a quality/security tool, minimalism is trust.

**Q: What does your CI do?**
A: Runs the test suite across Python 3.9/3.11/3.12 (AST shapes vary by version), then runs codehound on its own source — dogfooding — with `--exit-zero` so it reports without blocking.

**Q: Why test multiple Python versions?**
A: The `ast` module's node attributes change subtly between versions; the matrix proves the analyzer works on each supported version.

## ✅ Say this out loud
> *"It's packaged with a standard `pyproject.toml` and hatchling; `pip install` gives you a `codehound` command via a script entry point. It has zero runtime dependencies — pure standard library — which means no supply-chain risk and a fully auditable tool. CI runs pytest across Python 3.9, 3.11, and 3.12 because AST shapes vary by version, then dogfoods by scanning its own source with `--exit-zero`."*

Tomorrow: the capstone — you write codehound's seventh check from scratch.
