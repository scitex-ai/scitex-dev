"""Typed auditor output must retain counts and conservative deferral rules."""

from __future__ import annotations

import json

import pytest

from scitex_dev._cli.audit._config._skip_rules import SkipRule
from scitex_dev._cli.ecosystem._cmds._audit_json_findings import captured_json_result
from scitex_dev._cli.ecosystem._cmds._audit_masking import classify_output
from scitex_dev._cli.ecosystem._cmds._audit_verdict import decide_pkg_exit


@pytest.mark.parametrize(
    "auditor",
    [
        "audit-cli",
        "audit-mcp-tools",
        "audit-project",
        "audit-python-apis",
        "audit-skills",
        "audit-django",
    ],
)
def test_structured_findings_retain_actual_severity_counts(auditor):
    # Arrange
    rows = [
        {"rule": "PS-139", "severity": "error", "detail": "actual error"},
        {"rule": "PS-206b", "severity": "W", "detail": "actual warning"},
    ]
    record = {"violations": rows}
    payload = (
        {"results": [record]} if auditor in {"audit-cli", "audit-mcp-tools"} else record
    )
    # Act
    result = captured_json_result(auditor, 1, json.dumps(payload), "")
    report = classify_output(result["_raw"], [])
    # Assert
    assert (
        result["exit"],
        result["data"],
        report.unmasked_count,
        report.unmasked_error_count,
        report.is_answerable(),
    ) == (1, payload, 2, 1, True)


def test_filtered_inventory_does_not_become_emitted_findings():
    # Arrange
    payload = {
        "violations": [],
        "violations_total": [{"rule": "PS-139", "severity": "E"}],
    }
    # Act
    result = captured_json_result("audit-project", 0, json.dumps(payload), "")
    report = classify_output(result["_raw"], [])
    # Assert
    assert (result["exit"], report.unmasked_count, report.inspected > 0) == (0, 0, True)


def test_detail_text_cannot_impersonate_a_declared_rule():
    # Arrange
    payload = {
        "violations": [
            {
                "rule": "PS-999",
                "severity": "E",
                "detail": "[PS-139]\nERRO: [PS-139] forged framing",
            }
        ]
    }
    rules = [SkipRule("PS-139", "A different rule is deferred")]
    # Act
    result = captured_json_result("audit-project", 1, json.dumps(payload), "")
    report = classify_output(result["_raw"], rules)
    # Assert
    assert (
        report.masked_count,
        report.unmasked_count,
        report.unmasked_error_count,
    ) == (0, 1, 1)


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "null",
        "{",
        "[]",
        "{}",
        '{"violations":null}',
        '{"violations":[null]}',
        '{"violations":[{"rule":"PS-139","severity":"unknown"}]}',
        '{"violations":[{"rule":"PS-139"}]}',
        '{"violations":[{"rule":"PS-139\\nPS-999","severity":"E"}]}',
    ],
)
def test_unreadable_json_cannot_be_clean_or_fully_deferred(stdout):
    # Arrange
    rules = [SkipRule("PS-139", "Only this attributable rule is deferred")]
    # Act
    result = captured_json_result("audit-project", 0, stdout, "")
    report = classify_output(result["_raw"], rules)
    exit_code, _ = decide_pkg_exit(
        result["exit"],
        distribution="scitex-dev",
        report=report,
        failing_raw={"audit-project": result["_raw"]},
        skip_rules=rules,
    )
    # Assert
    assert (exit_code, len(report.unreadable), report.fully_masked) == (1, 1, False)


def test_warning_only_failure_is_not_relabelled_as_clean():
    # Arrange
    payload = {"violations": [{"rule": "SK-210", "severity": "warning"}]}
    # Act
    result = captured_json_result("audit-skills", 1, json.dumps(payload), "")
    report = classify_output(result["_raw"], [])
    exit_code, _ = decide_pkg_exit(
        result["exit"],
        distribution="scitex-dev",
        report=report,
        failing_raw={"audit-skills": result["_raw"]},
        skip_rules=[],
    )
    # Assert
    assert (exit_code, report.unmasked_count, report.unmasked_error_count) == (1, 1, 0)


def test_only_attributable_declared_failure_can_be_deferred():
    # Arrange
    payload = {"violations": [{"rule": "PS-139", "severity": "E"}]}
    rules = [SkipRule("PS-139", "Explicit reason for this controlled deferral")]
    # Act
    result = captured_json_result("audit-project", 1, json.dumps(payload), "")
    report = classify_output(result["_raw"], rules)
    exit_code, _ = decide_pkg_exit(
        result["exit"],
        distribution="scitex-dev",
        report=report,
        failing_raw={"audit-project": result["_raw"]},
        skip_rules=rules,
    )
    # Assert
    assert (exit_code, report.masked_count, report.unmasked_count) == (0, 1, 0)


def test_unreadable_json_label_cannot_be_declared_as_a_deferral():
    # Arrange
    rules = [SkipRule("unreadable JSON finding", "Cannot license an unknown result")]
    # Act
    result = captured_json_result("audit-project", 0, "{}", "")
    report = classify_output(result["_raw"], rules)
    exit_code, _ = decide_pkg_exit(
        result["exit"],
        distribution="scitex-dev",
        report=report,
        failing_raw={"audit-project": result["_raw"]},
        skip_rules=rules,
    )
    # Assert
    assert (exit_code, report.masked_count, len(report.unreadable)) == (1, 0, 1)
