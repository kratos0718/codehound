"""codehound - an AST-based static analyzer that hunts real bugs in Python code.

Twenty-two checks. Eight are each backed by a bug that was actually found
and fixed (or opened as a PR) in a popular open-source AI framework
(agno, crewAI, mem0, llama_index, accelerate, optuna, litellm). The rest
(CH007-CH009, CH012-CH022) are hardening rules verified against real
false positives across a ~29-framework validation corpus instead - see
docs/FINDINGS.md.
"""

from __future__ import annotations

from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import Check, Finding, scan_file, scan_path

__version__ = "1.5.0"

__all__ = [
    "ALL_CHECKS",
    "get_checks",
    "Check",
    "Finding",
    "scan_file",
    "scan_path",
    "__version__",
]
