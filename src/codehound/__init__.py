"""codehound - an AST-based static analyzer that hunts real bugs in Python code.

Six checks, each backed by a bug that was actually found and fixed in a popular
open-source AI framework (agno, crewAI, mem0, huggingface_hub).
"""

from __future__ import annotations

from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import Check, Finding, scan_file, scan_path

__version__ = "0.1.0"

__all__ = [
    "ALL_CHECKS",
    "get_checks",
    "Check",
    "Finding",
    "scan_file",
    "scan_path",
    "__version__",
]
