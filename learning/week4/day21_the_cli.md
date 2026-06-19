# Day 21 — The CLI: `argparse`, subcommands, formats & exit codes

> How codehound goes from a library to a command you run — and the exit-code design that lets it gate CI. Open `src/codehound/cli.py`.

---

## 1. `build_parser` — defining the interface (lines 57–92)
Uses the stdlib `argparse`. Two **subcommands** via `add_subparsers`:
- `codehound scan <path>` with flags `--select`, `--format {text,json,csv}`, `--include-tests`, `--exit-zero`, plus a global `--version`.
- `codehound list` — print the available checks.

The neat pattern: each subparser does `set_defaults(func=_cmd_scan)` (or `_cmd_list`). So `main` doesn't branch on the command name — it just calls `args.func(args)`:
```python
def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)
```
Adding a subcommand = add a parser + a `_cmd_*` function. `main` never changes. (Same open-for-extension spirit as the check registry.)

## 2. `_cmd_scan` — the workhorse (lines 14–48)
1. Parse `--select` into a list; `get_checks(selected)`. If nothing matches, print to **stderr** and return **2**.
2. Build the skip-dir set; if `--include-tests`, remove `tests`/`test`/`testing` from it.
3. `scan_path(...)` → findings.
4. Render by `--format`:
   - **text:** `f.as_text()` per finding, plus a summary count on **stderr**.
   - **json:** `json.dumps([f.as_dict() ...], indent=2)`.
   - **csv:** a header + one row per finding (quotes in messages sanitized).
5. **Exit code:** `1` if findings and not `--exit-zero`, else `0`.

## 3. Exit codes — the part that matters for CI
```python
if findings and not args.exit_zero:
    return 1
return 0
```
| Exit | Meaning |
|------|---------|
| `0` | clean (or `--exit-zero`) |
| `1` | issues found |
| `2` | no checks matched `--select` (usage error) |

**Why it matters:** CI tools treat **non-zero as failure**. So `codehound scan src` in a CI step *fails the build* when a new bug is introduced — that's how a linter becomes a *gate*, not just a report. `--exit-zero` lets you run it in "report but don't block" mode (codehound's own CI uses it for a self-scan, Day 23).

## 4. Why stdout vs stderr matters
Findings/JSON/CSV go to **stdout**; the human summary and errors go to **stderr**. That separation means you can pipe machine output cleanly: `codehound scan src --format json > report.json` captures *only* the JSON, while the summary still shows in your terminal.

## 5. 🔧 Exercise
```bash
PYTHONPATH=src python3 -m codehound.cli list
PYTHONPATH=src python3 -m codehound.cli scan src --format json > /tmp/r.json; echo $?
PYTHONPATH=src python3 -m codehound.cli scan src --select CH999; echo $?   # 2
```

## 6. 💬 Interview Q&A
**Q: How does codehound integrate with CI?**
A: Exit codes. It returns 1 when it finds issues, so a `codehound scan` step fails the build on a new bug. `--exit-zero` switches it to report-only.

**Q: What does exit code 2 mean?**
A: A usage problem — `--select` matched no checks. I distinguish it from "found bugs" (1) and "clean" (0) so scripts can tell a misconfiguration from a real finding.

**Q: Why send the summary to stderr?**
A: So stdout carries only the machine-readable findings/JSON/CSV and can be redirected cleanly, while humans still see the summary.

**Q: How is the command dispatched without a big if/else?**
A: Each subparser sets `func` via `set_defaults`, and `main` just calls `args.func(args)` — adding a command needs no change to `main`.

## ✅ Say this out loud
> *"The CLI is argparse with two subcommands, `scan` and `list`, dispatched by `set_defaults(func=...)` so `main` just calls `args.func`. `scan` picks checks, runs `scan_path`, and renders text/json/csv. The key design is exit codes — 0 clean, 1 issues found, 2 bad selection — so it gates CI by failing the build, with `--exit-zero` for report-only mode. Machine output goes to stdout, summaries to stderr, so it pipes cleanly."*

Tomorrow: the tests — and how they *prove* the false-positive guards work.
