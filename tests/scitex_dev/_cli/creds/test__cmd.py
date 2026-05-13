"""CLI smoke tests for scitex_dev._cli.creds._cmd."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("click")

import click
from click.testing import CliRunner

from scitex_dev._cli.creds import register_creds_commands
from scitex_dev._creds import _rotate


def _build():
    @click.group()
    def main():
        pass

    register_creds_commands(main)
    return main


def test_creds_help_runs():
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "--help"])
    assert res.exit_code == 0
    assert "rotate-all" in res.output
    assert "install-cron" in res.output


def test_creds_rotate_all_help_runs():
    runner = CliRunner()
    res = runner.invoke(_build(), ["creds", "rotate-all", "--help"])
    assert res.exit_code == 0
    assert "CLAUDE_CODE_CREDENTIALS_JSON" in res.output


def test_creds_rotate_all_silent_when_source_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: "/usr/bin/gh")
    runner = CliRunner()
    res = runner.invoke(
        _build(),
        ["creds", "rotate-all", "--source", str(tmp_path / "absent.json"), "--dry-run"],
    )
    # Silent exit 0 — no per-repo lines.
    assert res.exit_code == 0
    assert "would rotate" not in res.output


def test_creds_rotate_all_dry_run_emits_one_line_per_pkg(monkeypatch, tmp_path):
    src = tmp_path / "creds.json"
    src.write_text(
        json.dumps(
            {"claudeAiOauth": {"expiresAt": 9_999_999_999_999, "accessToken": "x"}}
        )
    )
    monkeypatch.setattr(
        _rotate,
        "ECOSYSTEM",
        {
            "pkg-a": {"github_repo": "o/a"},
            "pkg-b": {"github_repo": "o/b"},
        },
    )
    monkeypatch.setattr(_rotate, "get_local_path", lambda _: None)
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: "/usr/bin/gh")

    class _R:
        def __init__(self, rc=1, stdout="", stderr=""):
            self.returncode = rc
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(_rotate.subprocess, "run", lambda *a, **k: _R())

    runner = CliRunner()
    res = runner.invoke(
        _build(),
        ["creds", "rotate-all", "--source", str(src), "--dry-run"],
    )
    assert res.exit_code == 0, res.output
    assert "pkg-a" in res.output
    assert "pkg-b" in res.output
    assert "summary:" in res.output
