"""Tests for the ``scitex-dev gate`` CLI command (exit codes + JSON shape)."""

from __future__ import annotations

import json
import tempfile

from click.testing import CliRunner

from scitex_dev._cli._root import main


def test_gate_passes_on_existing_workdir_exit_zero():
    # Arrange
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        # Act
        res = runner.invoke(main, ["gate", "--stage=pre-submission", td, "--json"])
    # Assert
    assert res.exit_code == 0


def test_gate_json_reports_not_blocking_on_pass():
    # Arrange
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        # Act
        res = runner.invoke(main, ["gate", "--stage=pre-submission", td, "--json"])
        payload = json.loads(res.output.splitlines()[-1])
    # Assert
    assert payload["blocking"] is False


def test_gate_warn_default_missing_dir_exit_zero():
    # Arrange — builtin fails but is unenforced (no config) → advisory.
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "/no/such/dir"])
    # Assert
    assert res.exit_code == 0


def test_gate_enforced_missing_dir_exit_two():
    # Arrange — config in the workdir tree enforces the builtin.
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as td:
        import os
        from pathlib import Path

        cfgdir = Path(td) / ".scitex" / "dev"
        cfgdir.mkdir(parents=True)
        (cfgdir / "config.yaml").write_text(
            "gate:\n  enforce: [gate-workdir-present]\n", encoding="utf-8"
        )
        missing = Path(td) / "nope"
        # Act
        res = runner.invoke(
            main, ["gate", "--stage=pre-submission", str(missing)]
        )
    # Assert — enforced failure blocks with exit 2.
    assert res.exit_code == 2


def test_gate_list_needs_no_workdir():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission", "--list"])
    # Assert
    assert res.exit_code == 0


def test_gate_list_json_includes_builtin():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(
        main, ["gate", "--stage=pre-submission", "--list", "--json"]
    )
    ids = [c["id"] for c in json.loads(res.output.splitlines()[-1])]
    # Assert
    assert "gate-workdir-present" in ids


def test_gate_missing_workdir_without_list_is_usage_error():
    # Arrange
    runner = CliRunner()
    # Act
    res = runner.invoke(main, ["gate", "--stage=pre-submission"])
    # Assert — Click usage error exits 2 (missing required WORKDIR).
    assert res.exit_code == 2
