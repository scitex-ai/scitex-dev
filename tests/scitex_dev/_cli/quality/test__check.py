"""Smoke test for scitex_dev._cli.quality._check."""

from __future__ import annotations

from scitex_dev._cli.quality import _check


def test_check_module_callables_present():
    """All public quality CLI helpers exist as callables."""
    # Arrange
    # Act
    # Assert
    for name in (
        "audit_docs",
        "audit_scope",
        "audit_lines",
        "lint_pyproject_cli",
        "rtd_onboard_cli",
        "release_publish_cli",
        "audit_ecosystem",
    ):
        assert callable(getattr(_check, name)), f"{name} missing or not callable"


def test_lint_pyproject_cli_on_self(tmp_path, capsys):
    """lint_pyproject_cli runs end-to-end on the scitex-dev repo and returns an int."""
    # Arrange
    # Act
    # Assert
    import os

    rc = _check.lint_pyproject_cli(repo_root=os.getcwd())
    assert rc in (0, 1, 2)
