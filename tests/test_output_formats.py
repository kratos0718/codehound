"""Tests for the non-default output formats: SARIF and colored text.

Scan results themselves are covered by test_checks.py; these tests only
check that each format serializes a Finding correctly.
"""

from __future__ import annotations

from codehound.checks import ALL_CHECKS
from codehound.core import Finding
from codehound.sarif import to_sarif
from codehound.terminal import format_finding_text, format_summary


def _sample_finding() -> Finding:
    return Finding(path="pkg/mod.py", line=10, col=4, code="CH002", message="test message")


def test_sarif_has_required_top_level_shape():
    doc = to_sarif([_sample_finding()], ALL_CHECKS)
    assert doc["version"] == "2.1.0"
    assert "$schema" in doc
    assert len(doc["runs"]) == 1
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "codehound"


def test_sarif_includes_a_rule_entry_per_check():
    doc = to_sarif([], ALL_CHECKS)
    rule_ids = {r["id"] for r in doc["runs"][0]["tool"]["driver"]["rules"]}
    assert rule_ids == {c.code for c in ALL_CHECKS}


def test_sarif_result_location_and_1_indexed_column():
    doc = to_sarif([_sample_finding()], ALL_CHECKS)
    result = doc["runs"][0]["results"][0]
    assert result["ruleId"] == "CH002"
    loc = result["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "pkg/mod.py"
    # Finding.col is a 0-indexed ast col_offset; SARIF columns are 1-indexed.
    assert loc["region"]["startLine"] == 10
    assert loc["region"]["startColumn"] == 5


def test_sarif_with_no_findings_has_empty_results():
    doc = to_sarif([], ALL_CHECKS)
    assert doc["runs"][0]["results"] == []


def test_colored_text_contains_plain_text_content():
    finding = _sample_finding()
    colored = format_finding_text(finding, color=True)
    plain = format_finding_text(finding, color=False)
    assert plain == finding.as_text()
    assert "\033[" in colored
    assert "CH002" in colored
    assert "test message" in colored
    assert "pkg/mod.py" in colored


def test_summary_reports_correct_counts():
    findings = [
        Finding(path="a.py", line=1, col=0, code="CH001", message="x"),
        Finding(path="b.py", line=2, col=0, code="CH001", message="y"),
        Finding(path="c.py", line=3, col=0, code="CH002", message="z"),
    ]
    summary = format_summary(findings)
    assert "Found 3 issue(s)" in summary
    assert "CH001: 2" in summary
    assert "CH002: 1" in summary


def test_summary_with_no_findings():
    assert format_summary([]) == "Found 0 issue(s)"
