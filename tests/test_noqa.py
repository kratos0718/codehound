"""Tests for inline ``# noqa`` suppression."""

from __future__ import annotations

import tempfile
import os

from codehound.checks import get_checks
from codehound.core import _is_suppressed, _parse_noqa_lines, Finding, scan_file


def test_parse_noqa_lines_bare():
    source = "x = 1  # noqa\ny = 2\n"
    lines = _parse_noqa_lines(source)
    assert lines == {1: None}


def test_parse_noqa_lines_with_codes():
    source = "x = 1  # noqa: CH001, CH002\n"
    lines = _parse_noqa_lines(source)
    assert lines == {1: {"CH001", "CH002"}}


def test_parse_noqa_lines_case_insensitive():
    source = "x = 1  # NOQA: ch001\n"
    lines = _parse_noqa_lines(source)
    assert lines == {1: {"CH001"}}


def test_parse_noqa_lines_ignores_lines_without_it():
    source = "x = 1\ny = 2  # a regular comment\n"
    assert _parse_noqa_lines(source) == {}


def test_is_suppressed_bare_noqa_matches_any_code():
    finding = Finding(path="f.py", line=1, col=0, code="CH017", message="m")
    assert _is_suppressed(finding, {1: None}) is True


def test_is_suppressed_scoped_noqa_matches_listed_code_only():
    finding = Finding(path="f.py", line=1, col=0, code="CH017", message="m")
    assert _is_suppressed(finding, {1: {"CH017"}}) is True
    assert _is_suppressed(finding, {1: {"CH002"}}) is False


def test_is_suppressed_false_for_unrelated_line():
    finding = Finding(path="f.py", line=5, col=0, code="CH017", message="m")
    assert _is_suppressed(finding, {1: None}) is False


def test_scan_file_end_to_end_bare_noqa_suppresses_finding():
    code = (
        "import time\n"
        "async def f():\n"
        "    time.sleep(1)  # noqa\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        findings = scan_file(path, get_checks(["CH001"]))
        assert findings == []
    finally:
        os.unlink(path)


def test_scan_file_end_to_end_scoped_noqa_suppresses_only_that_code():
    code = (
        "import time\n"
        "async def f():\n"
        "    time.sleep(1)  # noqa: CH001\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        assert scan_file(path, get_checks(["CH001"])) == []
        # A noqa scoped to a different code doesn't suppress CH001.
        code2 = code.replace("# noqa: CH001", "# noqa: CH999")
        with open(path, "w") as fh:
            fh.write(code2)
        findings = scan_file(path, get_checks(["CH001"]))
        assert len(findings) == 1
    finally:
        os.unlink(path)


def test_scan_file_without_noqa_still_flags_normally():
    code = "import time\nasync def f():\n    time.sleep(1)\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as fh:
        fh.write(code)
        path = fh.name
    try:
        findings = scan_file(path, get_checks(["CH001"]))
        assert len(findings) == 1
    finally:
        os.unlink(path)
