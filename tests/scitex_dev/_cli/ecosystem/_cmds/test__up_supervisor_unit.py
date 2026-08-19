#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._cli.ecosystem._cmds._up_supervisor_unit.

The unit-text builder is pure (no I/O); the writer hits ``tmp_path``.
"""

from __future__ import annotations

import shlex
from pathlib import Path

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


# --------------------------------------------------------------------------- #
# Environment=PATH — the children's PATH, not the supervisor's own exec        #
# --------------------------------------------------------------------------- #


def test_build_unit_text_declares_a_path_for_its_children():
    # Arrange — the unit's children inherit its environment, and a periodic
    # job's body is a shell string calling `scitex-dev` by BARE NAME. With
    # no Environment=PATH the unit gets systemd's minimal --user PATH, which
    # excludes the venv, and every such job exits 127 after ~1s.
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "Environment=PATH=" in body


def test_unit_path_begins_with_the_directory_execstart_resolved_to():
    # Arrange — the invariant that actually matters. A PATH that merely
    # EXISTS does not help: it has to contain the bin directory holding the
    # console scripts, and the only directory guaranteed to be right is the
    # one ExecStart itself resolved to. Asserting "PATH is present" would
    # pass on a PATH that omits the venv — the exact bug this fixes.
    body = build_supervisor_unit_text()
    execstart = next(
        line[len("ExecStart=") :]
        for line in body.splitlines()
        if line.startswith("ExecStart=")
    )
    path_line = next(
        line[len("Environment=PATH=") :]
        for line in body.splitlines()
        if line.startswith("Environment=PATH=")
    )
    # Act
    first_entry = path_line.split(":")[0]
    # Assert
    assert first_entry == str(Path(shlex.split(execstart)[0]).parent)


def test_unit_path_retains_the_system_directories():
    # Arrange — jobs shell out to git / ssh / rsync too, so prepending the
    # venv must not REPLACE the system PATH.
    body = build_supervisor_unit_text()
    path_line = next(
        line[len("Environment=PATH=") :]
        for line in body.splitlines()
        if line.startswith("Environment=PATH=")
    )
    # Act
    entries = path_line.split(":")
    # Assert
    assert "/usr/bin" in entries and "/bin" in entries


def test_path_is_declared_before_execstart_is_not_required_but_both_present():
    # Arrange — systemd does not care about ordering within [Service]; this
    # test exists to state that BOTH lines are emitted, so a future edit that
    # drops one while keeping the other fails here rather than in production.
    # Act
    body = build_supervisor_unit_text()
    # Assert
    assert "ExecStart=" in body and "Environment=PATH=" in body

# EOF
