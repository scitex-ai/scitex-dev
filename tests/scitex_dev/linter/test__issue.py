"""The lightweight Issue preserves established consumer and pickle contracts."""

from scitex_dev.linter.checker import Issue
from scitex_dev.linter.spi import Issue as SpiIssue, Rule


def rule():
    return Rule("TEST-1", "error", "io", "Test rule", "Fix test rule")


def test_spi_issue_is_existing_checker_value():
    assert SpiIssue is Issue


def test_issue_pickle_retains_existing_import_identity():
    import pickle

    value = SpiIssue(rule(), 3, 2, "source")
    assert value.__class__.__module__ == "scitex_dev.linter.checker"
    assert pickle.loads(pickle.dumps(value)) == value
