#!/usr/bin/env python3
"""Regenerate the paper figures from the raw corpus scan results.

Both figures are single-series magnitude comparisons, so they use one hue
rather than a categorical palette: this keeps them legible in greyscale
print and removes any colour-vision-deficiency concern entirely.

Usage:
    python3 make_figures.py

Reads  : corpus_scan_results.csv
Writes : figures/fig1_defects_by_class.png
         figures/fig2_top_frameworks.png
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).parent
CSV = HERE / "corpus_scan_results.csv"
FIGDIR = HERE / "figures"

RULES = ["CH001", "CH002", "CH003", "CH004", "CH005", "CH006"]
RULE_LABELS = {
    "CH001": "CH001  blocking call in async",
    "CH002": "CH002  mutable default arg",
    "CH003": "CH003  deprecated utcnow",
    "CH004": "CH004  deprecated get_event_loop",
    "CH005": "CH005  unclosed file handle",
    "CH006": "CH006  fire-and-forget task",
}

# Single hue, dark enough to stay separable from the surface in greyscale.
INK = "#2F5C8F"
GRID = "#D8DEE6"
TEXT = "#1F2933"
MUTED = "#5A6672"

# IEEE single-column is ~3.5in wide.
COL_W = 3.5

plt.rcParams.update(
    {
        "font.size": 7.5,
        "font.family": "sans-serif",
        "axes.edgecolor": MUTED,
        "axes.labelcolor": TEXT,
        "text.color": TEXT,
        "xtick.color": MUTED,
        "ytick.color": TEXT,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    }
)


def load():
    df = pd.read_csv(CSV)
    for col in RULES + ["stars", "loc_py"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["total"] = df[RULES].sum(axis=1)
    return df


def _style(ax):
    """Recessive axes: no top/right spines, x-only grid behind the marks."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.6)
    ax.yaxis.grid(False)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def fig1(df):
    counts = {r: int(df[r].sum()) for r in RULES}
    total = sum(counts.values())
    order = sorted(RULES, key=lambda r: counts[r])  # ascending -> largest on top

    fig, ax = plt.subplots(figsize=(COL_W, 2.1))
    ax.barh(
        [RULE_LABELS[r] for r in order],
        [counts[r] for r in order],
        color=INK,
        height=0.62,
    )
    for i, r in enumerate(order):
        v = counts[r]
        ax.text(
            v + total * 0.012,
            i,
            f"{v}  ({100 * v / total:.1f}%)",
            va="center",
            fontsize=7,
            color=TEXT,
        )

    _style(ax)
    ax.set_xlabel("Defect instances")
    ax.set_xlim(0, max(counts.values()) * 1.28)
    fig.savefig(FIGDIR / "fig1_defects_by_class.png")
    plt.close(fig)
    print(f"fig1: {total} defects across {len(RULES)} rules")


# Repo names that mean nothing without their owner (e.g. "jina/serve" -> "serve").
GENERIC_NAMES = {"serve", "core", "sdk", "python-sdk", "client", "server", "api"}


def short_name(repo: str) -> str:
    owner, _, name = repo.partition("/")
    return f"{owner}/{name}" if name.lower() in GENERIC_NAMES else name


def fig2(df, top_n=12):
    d = df[df["total"] > 0].nlargest(top_n, "total").sort_values("total")
    names = [short_name(r) for r in d["repo"]]

    fig, ax = plt.subplots(figsize=(COL_W, 2.9))
    ax.barh(names, d["total"], color=INK, height=0.66)
    for i, v in enumerate(d["total"]):
        ax.text(v + d["total"].max() * 0.015, i, str(int(v)), va="center", fontsize=7)

    _style(ax)
    ax.set_xlabel("Defect instances")
    ax.set_xlim(0, d["total"].max() * 1.16)
    fig.savefig(FIGDIR / "fig2_top_frameworks.png")
    plt.close(fig)
    print(f"fig2: top {len(d)} of {int((df['total'] > 0).sum())} affected projects")


def main():
    FIGDIR.mkdir(exist_ok=True)
    df = load()
    print(
        f"corpus: {len(df)} repos | "
        f"{int(df['stars'].sum()):,} stars | "
        f"{int(df['loc_py'].sum()):,} LOC | "
        f"{int(df['total'].sum())} defects in {int((df['total'] > 0).sum())} repos"
    )
    fig1(df)
    fig2(df)


if __name__ == "__main__":
    main()
