"""codehound - an AST-based static analyzer that hunts real bugs in Python code.

One hundred checks. Eight are each backed by a bug that was actually
found and fixed (or opened as a PR) in a popular open-source AI framework
(agno, crewAI, mem0, llama_index, accelerate, optuna, litellm). The rest
(CH007-CH009, CH012-CH050, CH052-CH057, CH059-CH066, CH069-CH075,
CH078-CH083, CH086-CH090, CH092-CH100) are hardening rules verified
against real false positives across a ~29-framework validation corpus
instead - see docs/FINDINGS.md.

Also has the parts of a production-grade linter that don't require
rewriting the whole thing in Rust: inline `# noqa` suppression,
`[tool.codehound]` project config, `--fix` for the checks where the
rewrite is genuinely unambiguous, and scanning parallelized across a
process pool for large codebases.
"""

from __future__ import annotations

from codehound.checks import ALL_CHECKS, get_checks
from codehound.core import Check, Finding, scan_file, scan_files, scan_path

__version__ = "1.17.5"

__all__ = [
    "ALL_CHECKS",
    "get_checks",
    "Check",
    "Finding",
    "scan_file",
    "scan_files",
    "scan_path",
    "__version__",
]
