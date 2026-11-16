"""Conditional rules must respect the real detected availability values."""

import pytest

from scitex_dev.linter.checker import SciTeXChecker, lint_source
from scitex_dev.linter.config import LinterConfig
from scitex_dev.linter.rules import Rule


@pytest.fixture
def checker(tmp_path):
    return SciTeXChecker(
        ["pass"], filepath=str(tmp_path / "module.py"), config=LinterConfig()
    )


@pytest.mark.parametrize("owner", ["scitex", "figrecipe"])
def test_required_rule_emission_agrees_with_detected_package_value(checker, owner):
    # Arrange: use the detector's real snapshot, without changing it.
    rule = Rule(id="STX-GATE-PROBE", severity="warning", category="test",
                message="Required owner", suggestion="Probe input", requires=owner)
    expected = (rule.id,) * int(checker._available[owner])
    # Act
    checker._add(rule, 1, 0, "pass")
    # Assert
    assert tuple(issue.rule.id for issue in checker.issues) == expected


def test_unknown_required_package_does_not_emit_a_rule(checker):
    # Arrange
    rule = Rule(id="STX-GATE-PROBE", severity="warning", category="test",
                message="Unknown owner", suggestion="Probe input",
                requires="scitex_dev_unknown_owner")
    # Act
    checker._add(rule, 1, 0, "pass")
    # Assert
    assert checker.issues == []


def test_unconditional_rule_does_not_require_optional_packages(checker):
    # Arrange
    rule = Rule(id="STX-GATE-PROBE", severity="warning", category="test",
                message="No owner requirement", suggestion="Probe input")
    # Act
    checker._add(rule, 1, 0, "pass")
    # Assert
    assert tuple(issue.rule.id for issue in checker.issues) == (rule.id,)


def test_public_linter_keeps_unconditional_numeric_diagnostics():
    # Arrange
    source = "count = 12345\n"
    # Act
    issues = lint_source(source, filepath="module.py", config=LinterConfig())
    # Assert
    assert "STX-NL001" in {issue.rule.id for issue in issues}



def test_observer_preserves_public_issues_and_profiler(observe_lint):
    # Arrange
    import sys

    source = 'print("status")' + chr(10) + 'count = 12345' + chr(10)
    config = LinterConfig()
    previous = sys.getprofile()
    normal = lint_source(source, filepath="src/demo/core.py", config=config)
    # Act
    requests, observed = observe_lint(
        source, filepath="src/demo/core.py", config=config
    )
    # Assert
    assert (observed == normal, sys.getprofile() is previous,
            "PS-220" in {issue.rule.id for issue in observed}) == (True, True, True)


def test_real_session_request_is_filtered_by_real_availability(observe_lint):
    # Arrange
    from scitex_dev.linter._packages import detect

    source = chr(10).join([
        "import scitex as stx", "@stx.session", "def main():", "    return 0", ""
    ])
    # Act
    requests, emitted = observe_lint(source, config=LinterConfig())
    requested = tuple(rule.id for rule in requests if rule.id == "STX-S006")
    reported = tuple(issue.rule.id for issue in emitted
                     if issue.rule.id == "STX-S006")
    # Assert
    assert (requested, reported) == (
        ("STX-S006",), ("STX-S006",) * int(detect()["scitex"])
    )
