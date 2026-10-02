"""The real deferral inventory is framing; unknown findings remain unknown."""

import pytest

from scitex_dev._cli.audit._project._audit import audit_project
from scitex_dev._cli.ecosystem._cmds._audit_masking import classify_output


@pytest.mark.parametrize("count", [1, 12])
def test_deferred_inventory_is_answerable_and_preserves_entries(tmp_path, capfd, count):
    # Arrange
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-banner-fixture"\nversion = "0.0.0"\n')
    config = tmp_path / ".scitex/dev/config.yaml"
    config.parent.mkdir(parents=True)
    config.write_text("project-type: [pip, deferred]\n")
    for index in range(count):
        (tmp_path / f"owned_extra_{index:02}").mkdir()
    # Act
    exit_code = audit_project("scitex-banner-fixture", repo=tmp_path, rules={"PS-103"})
    output = capfd.readouterr().err
    report = classify_output(output, ())
    observed = (exit_code, f"{count} PS-103 finding(s) suppressed" in output,
                "project-type: deferred" in output, "Re-review when time permits" in output,
                tuple(f"    - owned_extra_{index:02}" in output for index in range(min(count, 10))),
                ("… +2 more" in output) == (count > 10), report.inspected > 0,
                report.is_answerable(), report.masked_count, report.unmasked_count)
    # Assert
    assert observed == (0, True, True, True, (True,) * min(count, 10), True, True, True, 0, 0)



@pytest.mark.parametrize("line", [
    "[defer] fixture: 1 PS-103 finding(s) suppressed",
    "ERRO: [E] anonymous failure without an attributable rule",
    "WARN: [unexpected] fixture: unknown finding",
])
def test_bracketed_unknowns_are_still_unreadable(line):
    # Arrange
    expected = ([line], False, False)
    # Act
    report = classify_output(line, ())
    # Assert
    assert (report.unreadable, report.is_answerable(), report.fully_masked) == expected


def test_actual_ps103_finding_is_still_unmasked():
    # Arrange
    line = "ERRO: [PS-103 §1] fixture: unexpected root entry"
    # Act
    report = classify_output(line, ())
    # Assert
    assert (report.unmasked, report.unmasked_error_count, report.is_answerable()) == ([line], 1, True)
