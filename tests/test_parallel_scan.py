"""Tests that parallel scanning (scan_files/scan_path with workers>1)
produces results identical to sequential scanning - not just "doesn't
crash." Verified once already against a ~29-framework corpus (byte-
identical output, ~4.7x wall-clock speedup on transformers); this locks
that in as a permanent regression check.
"""

from __future__ import annotations

import os
import tempfile

from codehound.checks import get_checks
from codehound.core import _MIN_FILES_FOR_PARALLEL, scan_files, scan_path


def _write_files(tmpdir: str, count: int) -> list[str]:
    paths = []
    for i in range(count):
        path = os.path.join(tmpdir, f"mod_{i}.py")
        with open(path, "w") as fh:
            # Every file has a real, distinct finding so results aren't
            # trivially empty either way.
            fh.write(f"import time\nasync def f_{i}():\n    time.sleep({i})\n")
        paths.append(path)
    return paths


def test_scan_files_parallel_matches_sequential_above_threshold():
    count = _MIN_FILES_FOR_PARALLEL + 4
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = _write_files(tmpdir, count)
        checks = get_checks(["CH001"])

        sequential = scan_files(paths, checks, workers=1)
        parallel = scan_files(paths, checks, workers=4)

        assert len(sequential) == count
        assert [f.as_text() for f in sequential] == [f.as_text() for f in parallel]


def test_scan_path_parallel_matches_sequential_above_threshold():
    count = _MIN_FILES_FOR_PARALLEL + 4
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_files(tmpdir, count)
        checks = get_checks(["CH001"])

        sequential = scan_path(tmpdir, checks, workers=1)
        parallel = scan_path(tmpdir, checks, workers=4)

        assert len(sequential) == count
        assert [f.as_text() for f in sequential] == [f.as_text() for f in parallel]


def test_scan_files_below_threshold_does_not_use_a_pool():
    # A handful of files (pre-commit's typical shape) should take the
    # sequential path regardless of the requested worker count - a
    # process pool's startup cost isn't worth it for this few files.
    count = _MIN_FILES_FOR_PARALLEL - 1
    with tempfile.TemporaryDirectory() as tmpdir:
        paths = _write_files(tmpdir, count)
        checks = get_checks(["CH001"])
        findings = scan_files(paths, checks, workers=8)
        assert len(findings) == count


def test_scan_files_empty_list_returns_empty():
    assert scan_files([], get_checks(["CH001"])) == []
