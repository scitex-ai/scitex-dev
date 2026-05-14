"""CLI smoke tests for scitex_dev._cli.creds._cmd."""

from __future__ import annotations

import json
import os
import stat

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.creds import register_creds_commands
from scitex_dev._creds._rotate import rotate_all


def _build():
    @click.group()
    def main():
        pass

    register_creds_commands(main)
    return main


@pytest.fixture
def fake_gh_on_path(tmp_path):
    """Place a real `gh` shim script on PATH that returns nonzero (variable
    missing) so the rotation always proceeds to the set-step.

    Yields the tmp path the gh script lives in. Restores PATH on exit.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text("#!/usr/bin/env bash\nexit 1\n")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    saved = os.environ.get("PATH")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{saved}"
    try:
        yield bin_dir
    finally:
        if saved is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved


def test_creds_help_runs_res_exit_code_0():
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "--help"])
    assert res.exit_code == 0


def test_creds_help_runs_rotate_all_in_res_output():
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "--help"])
    assert "rotate-all" in res.output


def test_creds_help_runs_install_cron_in_res_output():
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "--help"])
    assert "install-cron" in res.output


def test_creds_rotate_all_help_runs_res_exit_code_0():
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "rotate-all", "--help"])
    assert res.exit_code == 0


def test_creds_rotate_all_help_runs_claude_code_credentials_json_in_res_outp():
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "rotate-all", "--help"])
    assert "CLAUDE_CODE_CREDENTIALS_JSON" in res.output


def test_creds_rotate_all_silent_when_source_missing_res_exit_code_0(tmp_path, fake_gh_on_path):
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(
        _build(),
        ["creds", "rotate-all", "--source", str(tmp_path / "absent.json"), "--dry-run"],
    )
    # Silent exit 0 — no per-repo lines.
    assert res.exit_code == 0


def test_creds_rotate_all_silent_when_source_missing_would_rotate_not_in_res_output(tmp_path, fake_gh_on_path):
    # Arrange
    # Act
    # Assert
    runner = CliRunner()
    res = runner.invoke(
        _build(),
        ["creds", "rotate-all", "--source", str(tmp_path / "absent.json"), "--dry-run"],
    )
    # Silent exit 0 — no per-repo lines.
    assert "would rotate" not in res.output


def test_rotate_all_dry_run_emits_one_result_per_pkg_pkgs_pkg_a_pkg_b(tmp_path, fake_gh_on_path):
    """Drive `rotate_all` directly (not through the CLI) so we can inject
    a tiny ecosystem registry. A real `gh` shim on PATH supplies the
    subprocess side without mocks.
    """
    # Arrange
    # Act
    # Assert
    src = tmp_path / "creds.json"
    src.write_text(
        json.dumps(
            {"claudeAiOauth": {"expiresAt": 9_999_999_999_999, "accessToken": "x"}}
        )
    )
    eco = {
        "pkg-a": {"github_repo": "o/a"},
        "pkg-b": {"github_repo": "o/b"},
    }
    results = rotate_all(
        source_path=src,
        dry_run=True,
        ecosystem=eco,
        local_path_lookup=lambda _: None,
    )
    pkgs = {r.package for r in results}
    assert pkgs == {"pkg-a", "pkg-b"}
    # With a missing remote variable, the dry-run path is hit.
    statuses = {r.status for r in results}


def test_rotate_all_dry_run_emits_one_result_per_pkg_statuses_dry_run(tmp_path, fake_gh_on_path):
    """Drive `rotate_all` directly (not through the CLI) so we can inject
    a tiny ecosystem registry. A real `gh` shim on PATH supplies the
    subprocess side without mocks.
    """
    # Arrange
    # Act
    # Assert
    src = tmp_path / "creds.json"
    src.write_text(
        json.dumps(
            {"claudeAiOauth": {"expiresAt": 9_999_999_999_999, "accessToken": "x"}}
        )
    )
    eco = {
        "pkg-a": {"github_repo": "o/a"},
        "pkg-b": {"github_repo": "o/b"},
    }
    results = rotate_all(
        source_path=src,
        dry_run=True,
        ecosystem=eco,
        local_path_lookup=lambda _: None,
    )
    pkgs = {r.package for r in results}
    # With a missing remote variable, the dry-run path is hit.
    statuses = {r.status for r in results}
    assert statuses == {"dry-run"}
