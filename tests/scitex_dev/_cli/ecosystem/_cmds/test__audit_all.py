"""Smoke import test for `scitex_dev._cli.ecosystem._cmds._audit_all`.

Satisfies the PS-202 mirror requirement at the package-directory
level. Per-feature behavioural tests for the ecosystem _cmds modules
live alongside the features they exercise (test__bulk.py,
test__categories.py, etc., in the parent directory); this file is the
minimal seed that gives the mirror dir a matching test_*.py file so
audit-project's PS-202/PS-204/PS-207 trio stays clean. Extend with
behavioural tests as the audit-all command surface grows test-worthy
seams.
"""

from __future__ import annotations


def test_audit_all_module_imports_cleanly() -> None:
    """The audit-all CLI command module must import without side-effects."""
    # Arrange
    module_name = "scitex_dev._cli.ecosystem._cmds._audit_all"
    # Act
    import importlib

    mod = importlib.import_module(module_name)
    # Assert
    assert mod.__name__ == module_name
