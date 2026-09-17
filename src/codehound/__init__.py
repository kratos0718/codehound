"""codehound - an AST-based static analyzer that hunts real bugs in Python code.

Twenty checks. Seven are each backed by a bug that was actually found and
fixed in a popular open-source AI framework (agno, crewAI, mem0,
llama_index, accelerate). The rest (CH007-CH009, CH011-CH020) are
hardening rules verified against real false positives across a
~20-framework validation corpus instead - see docs/FINDINGS.md.
"""

from __future__ import annotations

from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import Check, Finding, scan_file, scan_path

__version__ = "1.4.1"

__all__ = [
    "ALL_CHECKS",
    "get_checks",
    "Check",
    "Finding",
    "scan_file",
    "scan_path",
    "__version__",
]
