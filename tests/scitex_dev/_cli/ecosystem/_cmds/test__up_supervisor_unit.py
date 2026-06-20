#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._cli.ecosystem._cmds._up_supervisor_unit.

The unit-text builder is pure (no I/O); the writer hits ``tmp_path``.
"""

from __future__ import annotations

from scitex_dev._cli.ecosystem._cmds._up_supervisor_unit import (
    SUPERVISOR_UNIT_NAME,
    build_supervisor_unit_text,
    write_supervisor_unit,
)


# --------------------------------------------------------------------------- #
# SUPERVISOR_UNIT_NAME                                                         #
# --------------------------------------------------------------------------- #


def test_supervisor_unit_name_is_scitex_dev_ecosystem_service():
    # Arrange
    # Act
    # Assert — this is the operator-approved canonical filename.
    assert SUPERVISOR_UNIT_NAME == "scitex-dev-ecosystem.service"


# --------------------------------------------------------------------------- #
# build_supervisor_unit_text                                                   #
# --------------------------------------------------------------------------- #


def test_build_unit_text_is_type_simple():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "Type=simple" in body


def test_build_unit_text_carries_restart_always():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "Restart=always" in body


def test_build_unit_text_exposes_execreload_sighup():
    # Arrange — ``systemctl --user reload`` must SIGHUP $MAINPID so the
    # supervisor's reload handler triggers reconcile().
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "ExecReload=/bin/kill -HUP $MAINPID" in body


def test_build_unit_text_killsignal_sigterm():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "KillSignal=SIGTERM" in body


def test_build_unit_text_timeoutstopsec_30s():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "TimeoutStopSec=30s" in body


def test_build_unit_text_journal_logging():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "StandardOutput=journal" in body


def test_build_unit_text_wanted_by_default_target():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "WantedBy=default.target" in body


def test_build_unit_text_execstart_calls_ecosystem_run():
    # Arrange
    # Act
    body = build_supervisor_unit_text()
    # Assert — the ExecStart line carries the `ecosystem run` invocation.
    assert "ecosystem run" in body


# --------------------------------------------------------------------------- #
# write_supervisor_unit                                                        #
# --------------------------------------------------------------------------- #


def test_write_supervisor_unit_creates_file(tmp_path):
    # Arrange
    # Act
    path = write_supervisor_unit(tmp_path)
    # Assert
    assert path.exists()


def test_write_supervisor_unit_uses_canonical_filename(tmp_path):
    # Arrange
    # Act
    path = write_supervisor_unit(tmp_path)
    # Assert
    assert path.name == SUPERVISOR_UNIT_NAME


def test_write_supervisor_unit_is_idempotent(tmp_path):
    # Arrange
    first = write_supervisor_unit(tmp_path).read_text(encoding="utf-8")
    # Act
    second = write_supervisor_unit(tmp_path).read_text(encoding="utf-8")
    # Assert
    assert first == second


def test_write_supervisor_unit_creates_parent(tmp_path):
    # Arrange — target a nested dir the writer must create.
    nested = tmp_path / "a" / "b" / "c"
    # Act
    write_supervisor_unit(nested)
    # Assert
    assert nested.is_dir()


# EOF
