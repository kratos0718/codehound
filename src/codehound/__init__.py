"""codehound - an AST-based static analyzer that hunts real bugs in Python code.

Seven checks. Six are each backed by a bug that was actually found and
fixed in a popular open-source AI framework (agno, crewAI, mem0,
llama_index, huggingface_hub). The seventh (CH007) is a hardening rule
verified against real false positives instead - see docs/FINDINGS.md.
"""

from __future__ import annotations

from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import Check, Finding, scan_file, scan_path

__version__ = "1.1.0"

__all__ = [
    "ALL_CHECKS",
    "get_checks",
    "Check",
    "Finding",
    "scan_file",
    "scan_path",
    "__version__",
]
