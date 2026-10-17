"""The lightweight Issue preserves established consumer and pickle contracts."""

from scitex_dev.linter.checker import Issue
from scitex_dev.linter.spi import Issue as SpiIssue, Rule


def rule():
    return Rule("TEST-1", "error", "io", "Test rule", "Fix test rule")


def test_spi_issue_is_existing_checker_value():
    # Arrange
    # Act
    same = SpiIssue is Issue
    # Assert
    assert same


def test_issue_pickle_retains_existing_import_identity():
    # Arrange
    # Act
    value = SpiIssue(rule(), 3, 2, "source")
    # Assert
    assert value.__class__.__module__ == "scitex_dev.linter.checker"


def test_issue_pickle_round_trip_preserves_equality():
    # Arrange
    import pickle

    # Act
    value = SpiIssue(rule(), 3, 2, "source")
    # Assert
    assert pickle.loads(pickle.dumps(value)) == value
