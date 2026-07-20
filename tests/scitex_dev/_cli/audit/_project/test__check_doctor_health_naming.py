# -*- coding: utf-8 -*-
"""Tests for `_check_doctor_health_naming.py` (PS-218).

The ecosystem health-check verb standardizes on `doctor`; `health` is a
deprecated alias only. PS-218 fires when a leaf ships a `health` command
as its PRIMARY health-check verb (no `doctor` command registered). Each
test builds a REAL temp `src/` tree (no mocks) then asserts whether
PS-218 fires.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_doctor_health_naming import (
    check_ps218_doctor_health_naming,
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


# --- PS-218 fires (positive case) -------------------------------------------


def test_ps218_fires_on_health_command_without_doctor(tmp_path):
    # Arrange — a `health` click command and no `doctor` command
    _write_cli(
        tmp_path,
        'import click\n\n\n@main.command("health")\ndef health():\n    ...\n',
    )
    out: list = []
    # Act
    check_ps218_doctor_health_naming(tmp_path, _StubViolation, out)
    # Assert
    assert "PS-218" in _codes(out)


# --- PS-218 silent (negative cases) -----------------------------------------


def test_ps218_silent_on_doctor_command(tmp_path):
    # Arrange — a `doctor` command (canonical verb), no `health`
    _write_cli(
        tmp_path,
        'import click\n\n\n@main.command("doctor")\ndef doctor():\n    ...\n',
    )
    out: list = []
    # Act
    check_ps218_doctor_health_naming(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps218_silent_when_health_alias_kept_alongside_doctor(tmp_path):
    # Arrange — canonical `doctor` plus a retained `health` deprecation alias
    _write_cli(
        tmp_path,
        'import click\n\n\n@main.command("doctor")\ndef doctor():\n    ...\n\n\n'
        '@main.command("health", hidden=True)\ndef health():\n    ...\n',
    )
    out: list = []
    # Act
    check_ps218_doctor_health_naming(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


def test_ps218_silent_on_non_cli_def_health(tmp_path):
    # Arrange — a bare `def health(request)` (e.g. a Django view), no command
    _write_cli(
        tmp_path,
        "def health(request):\n    return {'ok': True}\n",
    )
    out: list = []
    # Act
    check_ps218_doctor_health_naming(tmp_path, _StubViolation, out)
    # Assert
    assert out == []


# EOF
