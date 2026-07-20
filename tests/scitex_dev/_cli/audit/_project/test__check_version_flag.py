# -*- coding: utf-8 -*-
"""Tests for `_check_version_flag.py` (PS-219).

The ecosystem version surface standardizes on the `--version` / `-V`
flag; a `version` SUBCOMMAND is non-conforming. PS-219 fires when a leaf
exposes version ONLY as a subcommand (no `--version` flag anywhere).
Crucially it must NOT fire on a package that ships the flag, even when it
keeps a hidden `version` deprecation stub (the scitex-io end-state). Each
test builds a REAL temp `src/` tree (no mocks).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_version_flag import (
    check_ps219_version_flag,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _write_cli(repo: Path, body: str) -> None:
    cli = repo / "src" / "pkg" / "_cli"
    cli.mkdir(parents=True, exist_ok=True)
    cli.joinpath("_main.py").write_text(body, encoding="utf-8")


def _codes(out: list) -> set[str]:
    return {v.rule for v in out}


# --- PS-219 fires (positive case) -------------------------------------------


def test_ps219_fires_on_version_subcommand_without_flag(tmp_path):
    # Arrange — version exposed ONLY as a subcommand, no `--version` flag
    _write_cli(
        tmp_path,
        'import click\n\n\n@main.command("version")\ndef version():\n'
        '    click.echo("1.0")\n',
    )
    out: list = []
    # Act
    check_ps219_version_flag(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-219" in _codes(out)


# --- PS-219 silent (negative cases) -----------------------------------------


def test_ps219_silent_on_version_option_flag(tmp_path):
    # Arrange — canonical `@click.version_option(... --version ...)`, no subcommand
    _write_cli(
        tmp_path,
        'import click\n\n\n@click.version_option("1.0", "--version", "-V")\n'
        "def main():\n    ...\n",
    )
    out: list = []
    # Act
    check_ps219_version_flag(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps219_silent_when_flag_present_alongside_hidden_version_stub(tmp_path):
    # Arrange — the scitex-io end-state: `--version` flag AND a hidden
    # `version` deprecation subcommand. Must NOT be flagged (no false positive).
    _write_cli(
        tmp_path,
        'import click\n\n\n@click.version_option("1.0", "--version", "-V")\n'
        "def main():\n    ...\n\n\n"
        '@click.command("version", hidden=True)\ndef version(ctx):\n'
        '    """(deprecated) Use `pkg --version` instead."""\n    ...\n',
    )
    out: list = []
    # Act
    check_ps219_version_flag(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
