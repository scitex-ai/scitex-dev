"""Terminal styling must not hide findings or become a synthetic rule id."""

import json
import os
import subprocess
import sys

import click
import pytest

from scitex_dev._cli.audit._config._skip_rules import SkipRule
from scitex_dev._cli.ecosystem._cmds._audit_masking import (
    classify_output,
    is_error_line,
    is_violation_line,
    label_masked_lines,
)

_ERROR = "ERRO:   [PA-307 §3 test-quality] pkg: tests/x.py:1: two assertions"
_WARN = "WARN:   [PA-101 §1 all-missing] pkg: src/pkg/__init__.py: declare __all__"


@pytest.mark.parametrize("color", [31, 33, 1])
def test_colored_error_finding_is_classified(color):
    # Arrange
    text = f"\x1b[{color}m{_ERROR}\x1b[0m"
    # Act
    report = classify_output(text, [])
    # Assert
    assert (report.unmasked_count, report.unmasked_error_count) == (1, 1)


def test_colored_warning_keeps_warning_severity():
    # Arrange
    text = f"\x1b[33m{_WARN}\x1b[0m"
    # Act
    report = classify_output(text, [])
    # Assert
    assert (report.unmasked_count, report.unmasked_error_count) == (1, 0)


def test_color_inside_rule_token_is_readable():
    # Arrange
    text = _ERROR.replace("PA-307", "\x1b[31mPA-307\x1b[0m")
    # Act
    report = classify_output(text, [])
    # Assert
    assert (report.unmasked_count, len(report.unreadable)) == (1, 0)


def test_color_codes_cannot_supply_missing_rule_identity():
    # Arrange: the SGR color number is not an attributable rule identifier.
    text = "\x1b[31mERRO:   [E] pkg: rule identity missing\x1b[0m"
    # Act
    report = classify_output(text, [])
    # Assert
    assert (len(report.unreadable), report.unmasked_count) == (1, 0)


def test_colored_headline_stays_framing_only():
    # Arrange
    text = "\x1b[31mERRO: pkg: Python API: 6 violation(s)\x1b[0m"
    # Act
    report = classify_output(text, [])
    # Assert
    assert (report.inspected, report.unmasked_count, len(report.unreadable)) == (
        1,
        0,
        0,
    )


def test_original_colored_error_is_retained_verbatim():
    # Arrange
    text = f"\x1b[31m{_ERROR}\x1b[0m"
    # Act
    report = classify_output(text, [])
    # Assert
    assert report.unmasked == [text]


def test_colored_findings_are_detected_by_public_predicates():
    # Arrange
    text = f"\x1b[31m{_ERROR}\x1b[0m"
    # Act
    observed = is_violation_line(text), is_error_line(text)
    # Assert
    assert observed == (True, True)


def test_colored_rule_matches_only_explicit_existing_declaration():
    # Arrange: an owned classifier control, not a repository skip change.
    text = _ERROR.replace("PA-307", "\x1b[31mPA-307\x1b[0m")
    rules = [SkipRule(rule="PA-307", reason="owned classifier control")]
    # Act
    report = classify_output(text, rules)
    # Assert
    assert (report.masked_count, report.unmasked_count) == (1, 0)


def test_colored_unknown_still_blocks_fully_masked_claim():
    # Arrange
    text = f"{_ERROR}\n\x1b[31mERRO: [E] identity missing\x1b[0m"
    rules = [SkipRule(rule="PA-307", reason="owned classifier control")]
    # Act
    report = classify_output(text, rules)
    # Assert
    assert not report.fully_masked


def test_unmasked_colored_output_is_byte_preserved():
    # Arrange
    text = f"\x1b[31m{_ERROR}\x1b[0m"
    report = classify_output(text, [])
    # Act
    result = label_masked_lines(text, report)
    # Assert
    assert result == text


def test_real_sub_auditor_transport_retains_error_count(tmp_path):
    # Arrange: audited fixture source is parsed, never imported/executed.
    (tmp_path / "pyproject.toml").write_text('[project]\nname="scitex-dev"\n')
    package = tmp_path / "src/scitex_dev"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__all__ = []\n")
    tests = tmp_path / "tests/scitex_dev"
    tests.mkdir(parents=True)
    (tests / "test_control.py").write_text(
        "def test_owned_multiple_assertions():\n"
        "    # Arrange\n    value = 1\n    # Act\n    result = value + 1\n"
        "    # Assert\n    assert result == 2\n    assert value == 1\n"
    )
    # Act: the real CLI emits its own colorized findings, not a mock logger.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scitex_dev",
            "ecosystem",
            "audit-python-apis",
            "scitex-dev",
            "--path",
            str(tmp_path),
            "--rule",
            "PA-307",
        ],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        check=False,
    )
    raw = result.stdout + "\n" + result.stderr
    report = classify_output(raw, [])
    plain = click.unstyle(raw)
    observed = (
        result.returncode != 0,
        "[PA-307" in plain,
        report.unmasked_error_count,
        len(report.unreadable),
    )
    # Assert
    assert observed == (True, True, 1, 0), json.dumps({"raw": raw})
