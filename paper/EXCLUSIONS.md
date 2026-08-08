# Corpus exclusions

This file documents repositories that were considered for the corpus but excluded
from the analysis set, and why. It exists so the corpus in
`corpus_scan_results.csv` is reproducible and the denominator in any prevalence
figure is unambiguous.

## mindsdb/mindsdb — excluded

**Pinned commit:** `a20c2f82d0186ba9b19ae84a5de148e418da9cc2` (2026-06-12)

**Reason:** at the pinned commit the repository contains no Python source in its
main tree. It tracks 37 files and carries a `.gitmodules` that delegates all
implementation to four separate repositories:

| Submodule path | Upstream repository |
|---|---|
| `frontend` | `mindsdb/cowork` |
| `backend/core_api` | `mindsdb/cowork-server` |
| `backend/core_agent` | `mindsdb/anton` |
| `backend/data-vault` | `mindsdb/data-vault` |

The original scan recorded zero findings across all six checks and an empty
`loc_py`. That is a **non-observation, not a clean result**: the analyzer was
correct that there was nothing to analyze, but the repository was never
meaningfully scanned. Retaining it as "a framework analyzed with zero defects"
would inflate the denominator of every prevalence statistic.

The repository was therefore removed from `corpus_scan_results.csv`. Analysing it
properly would require recursively cloning the four submodules, which changes the
unit of analysis from "one popular framework repository" to "four
implementation repositories," and so was left out of scope rather than
silently mixed into the corpus.

**Effect on reported figures:** the analysis set is **28 repositories**, not 29.
Defect counts are unaffected (mindsdb contributed none). Any statement of the
form "N of M frameworks" uses M = 28.

## Data corrections applied at the same time

Two star counts were recorded as `?` in the original scan and have been filled
from the GitHub API:

| Repository | Recorded | Corrected |
|---|---|---|
| `explodinggradients/ragas` | `?` | 15,181 |
| `mindsdb/mindsdb` | `?` | 39,528 (subsequently excluded) |

## Corrected corpus totals

| Metric | Value |
|---|---|
| Repositories analysed | 28 |
| Combined GitHub stars | 1,299,231 |
| Python LOC analysed | 6,386,365 |
| Total defect instances | 1,377 |
| Repositories with ≥1 defect | 24 of 28 |

Per-class distribution: CH002 742 (53.9%), CH004 286 (20.8%), CH006 262 (19.0%),
CH003 55 (4.0%), CH001 22 (1.6%), CH005 10 (0.7%).
