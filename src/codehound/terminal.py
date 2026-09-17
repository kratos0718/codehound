"""Colored text output for a terminal, plain text everywhere else.

Color only when stdout is actually a terminal, and never when ``NO_COLOR``
is set (https://no-color.org) or ``TERM=dumb`` - the same convention ruff,
eslint, and most modern CLI tools follow, so piping to a file or into `less`
never ends up with raw escape codes in it.
"""

from __future__ import annotations

import os
import sys

_RED = "\033[31m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _color_enabled(stream=None) -> bool:
    stream = stream or sys.stdout
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def format_finding_text(finding, color: bool) -> str:
    if not color:
        return finding.as_text()
    return (
        f"{_CYAN}{finding.path}{_RESET}:{_DIM}{finding.line}:{finding.col}{_RESET}: "
        f"{_RED}{_BOLD}{finding.code}{_RESET} {finding.message}"
    )


def format_findings_text(findings, stream=None) -> list[str]:
    color = _color_enabled(stream)
    return [format_finding_text(f, color) for f in findings]


def format_summary(findings, stream=None) -> str:
    color = _color_enabled(stream)
    counts: dict[str, int] = {}
    for f in findings:
        counts[f.code] = counts.get(f.code, 0) + 1
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
    count_str = str(len(findings))
    if color and findings:
        count_str = f"{_YELLOW}{_BOLD}{count_str}{_RESET}"
    line = f"Found {count_str} issue(s)"
    if summary:
        line += f" ({summary})"
    return line
