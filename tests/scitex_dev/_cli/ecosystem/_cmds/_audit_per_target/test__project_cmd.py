"""Tests for `ecosystem audit-project` (`_project_cmd.py`).

Registration smoke test plus the target-tree resolution regression
(operator directive 2026-07-21): with no `--path`, the command must
audit the CURRENT checkout when the cwd is inside a checkout of
DISTRIBUTION — never silently prefer the registry's `local_path` (the
wrong-tree incident: a CI run graded the operator's develop checkout
instead of the CI checkout the test lived in).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`
against a real `git init`-ed temp checkout.
"""

from __future__ import annotations

import json as _json
import os
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _make_group():
    @click.group()
    def root():
        pass

    register_ecosystem_commands(root)
    return root


@contextmanager
def _chdir(target: Path):
    """`os.chdir` to `target`, restoring the previous CWD on exit."""
    previous = Path.cwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(previous)


def _make_checkout(root: Path, distribution: str) -> Path:
    """A real git checkout shaped like `distribution`'s (src layout)."""
    import_name = distribution.replace("-", "_")
    pkg = root / "src" / import_name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{distribution}"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "-C", str(root), "init", "-q"], capture_output=True, check=True
    )
    return root


def _json_from_output(text: str) -> dict:
    """Parse the JSON payload out of the command output (skip any preamble)."""
    return _json.loads(text[text.index("{"):])


def test_audit_project_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(_make_group(), ["ecosystem", "audit-project", "--help"])
    # Assert
    assert result.exit_code == 0


def test_audit_project_no_path_resolves_the_current_checkout(tmp_path):
    """No `--path` + cwd inside the checkout → THAT tree is audited."""
    # Arrange — a checkout of a distribution the registry has never heard of.
    checkout = _make_checkout(tmp_path / "co", "demo-target-tree-pkg")
    runner = CliRunner()
    # Act
    with _chdir(checkout):
        result = runner.invoke(
            _make_group(),
            ["ecosystem", "audit-project", "demo-target-tree-pkg", "--json"],
        )
    payload = _json_from_output(result.output)
    # Assert
    assert payload["resolved_path"] == str(checkout.resolve())


def test_audit_project_no_path_reports_the_cwd_rule(tmp_path):
    """The payload names the `cwd` rule so the resolution is diagnosable."""
    # Arrange
    checkout = _make_checkout(tmp_path / "co", "demo-target-tree-pkg")
    runner = CliRunner()
    # Act
    with _chdir(checkout):
        result = runner.invoke(
            _make_group(),
            ["ecosystem", "audit-project", "demo-target-tree-pkg", "--json"],
        )
    payload = _json_from_output(result.output)
    # Assert
    assert payload["resolved_via"] == "cwd"


def test_audit_project_explicit_path_still_wins_over_cwd(tmp_path):
    """`--path` outranks the cwd checkout (rule a over rule b)."""
    # Arrange — cwd inside one checkout, --path pointing at another.
    explicit = _make_checkout(tmp_path / "explicit", "demo-target-tree-pkg")
    elsewhere = _make_checkout(tmp_path / "elsewhere", "demo-target-tree-pkg")
    runner = CliRunner()
    # Act
    with _chdir(elsewhere):
        result = runner.invoke(
            _make_group(),
            [
                "ecosystem",
                "audit-project",
                "demo-target-tree-pkg",
                "--path",
                str(explicit),
                "--json",
            ],
        )
    payload = _json_from_output(result.output)
    # Assert
    assert payload["resolved_path"] == str(explicit.resolve())
