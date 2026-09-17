"""SARIF 2.1.0 output, so a `codehound` run can feed GitHub's Code Scanning
tab directly (``github/codeql-action/upload-sarif``) instead of only being
readable as CI log text.

Deliberately minimal - just the fields GitHub's ingester actually needs:
one ``tool.driver`` with a ``rules`` array (so finding codes get a name and
description in the UI instead of a bare code), and one ``result`` per
finding with a single physical location. No fingerprinting, no nested
regions, no multi-run merging - those are real SARIF features this
doesn't need yet.
"""

from __future__ import annotations

from codehound import __version__
from codehound.core import Check, Finding

SARIF_SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json"


def _rule(check_cls: type[Check]) -> dict:
    return {
        "id": check_cls.code,
        "name": check_cls.name,
        "shortDescription": {"text": check_cls.description},
        "helpUri": "https://github.com/kratos0718/codehound#the-checks",
        "properties": {"tags": ["correctness", "codehound"]},
    }


def _result(finding: Finding) -> dict:
    return {
        "ruleId": finding.code,
        "level": "error",
        "message": {"text": finding.message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": finding.path.replace("\\", "/")},
                    "region": {
                        "startLine": max(finding.line, 1),
                        "startColumn": max(finding.col + 1, 1),
                    },
                }
            }
        ],
    }


def to_sarif(findings: list[Finding], all_checks: list[type[Check]]) -> dict:
    return {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "codehound",
                        "informationUri": "https://github.com/kratos0718/codehound",
                        "version": __version__,
                        "rules": [_rule(c) for c in all_checks],
                    }
                },
                "results": [_result(f) for f in findings],
            }
        ],
    }
