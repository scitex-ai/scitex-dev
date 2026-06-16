#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev._supervisor._state — atomic write + tolerant read.

Real fakes only (PA-306 / STX-NM); the module's behaviour against the
real filesystem is what we care about, and ``tmp_path`` is the cleanest
seam.
"""

from __future__ import annotations

import json
import os

import pytest

from scitex_dev._supervisor._state import (
    SupervisorState,
    default_state_dir,
    default_state_path,
    read_state,
    write_state_atomically,
)


@pytest.fixture
def restore_environ():
    """Snapshot + restore ``os.environ`` around a test.

    Real env manipulation (no mocks) — replaces ``monkeypatch.setenv`` /
    ``delenv`` per PA-306. Tests mutate the yielded mapping directly; it is
    restored verbatim afterwards so XDG_STATE_HOME / HOME don't leak into
    sibling tests.
    """
    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


# --------------------------------------------------------------------------- #
# default_state_dir / default_state_path                                      #
# --------------------------------------------------------------------------- #


def test_default_state_dir_honours_xdg_state_home(restore_environ, tmp_path):
    # Arrange
    restore_environ["XDG_STATE_HOME"] = str(tmp_path)
    # Act
    got = default_state_dir()
    # Assert
    assert got == tmp_path / "scitex-ecosystem"


def test_default_state_dir_falls_back_to_local_state_when_no_xdg(
    restore_environ, tmp_path
):
    # Arrange
    restore_environ.pop("XDG_STATE_HOME", None)
    restore_environ["HOME"] = str(tmp_path)
    # Act
    got = default_state_dir()
    # Assert
    assert got == tmp_path / ".local" / "state" / "scitex-ecosystem"


def test_default_state_path_filename_is_state_json(restore_environ, tmp_path):
    # Arrange
    restore_environ["XDG_STATE_HOME"] = str(tmp_path)
    # Act
    got = default_state_path()
    # Assert
    assert got.name == "state.json"


# --------------------------------------------------------------------------- #
# SupervisorState.to_json                                                      #
# --------------------------------------------------------------------------- #


def test_supervisor_state_to_json_is_valid_json():
    # Arrange
    s = SupervisorState(pid=1234, started_at=1.0, written_at=2.0)
    # Act
    parsed = json.loads(s.to_json())
    # Assert
    assert parsed["pid"] == 1234


def test_supervisor_state_to_json_includes_schema_version():
    # Arrange
    # Act
    parsed = json.loads(SupervisorState().to_json())
    # Assert
    assert parsed["schema_version"] == 1


def test_supervisor_state_to_json_includes_children_field():
    # Arrange
    s = SupervisorState(children=[{"name": "a", "status": "running"}])
    # Act
    parsed = json.loads(s.to_json())
    # Assert
    assert parsed["children"][0]["name"] == "a"


# --------------------------------------------------------------------------- #
# write_state_atomically                                                       #
# --------------------------------------------------------------------------- #


def test_write_state_atomically_creates_file(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    # Act
    write_state_atomically(SupervisorState(pid=1), path)
    # Assert
    assert path.exists()


def test_write_state_atomically_creates_parent_dir(tmp_path):
    # Arrange
    path = tmp_path / "nested" / "deeper" / "state.json"
    # Act
    write_state_atomically(SupervisorState(), path)
    # Assert
    assert path.parent.is_dir()


def test_write_state_atomically_overwrites_existing(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    write_state_atomically(SupervisorState(pid=1), path)
    # Act
    write_state_atomically(SupervisorState(pid=2), path)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    # Assert
    assert parsed["pid"] == 2


def test_write_state_atomically_leaves_no_tmp_file(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    # Act
    write_state_atomically(SupervisorState(), path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".state.")]
    # Assert
    assert leftovers == []


# --------------------------------------------------------------------------- #
# read_state — tolerant                                                       #
# --------------------------------------------------------------------------- #


def test_read_state_returns_none_for_missing_path(tmp_path):
    # Arrange
    path = tmp_path / "nope.json"
    # Act
    got = read_state(path)
    # Assert
    assert got is None


def test_read_state_returns_none_for_empty_file(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    path.write_text("", encoding="utf-8")
    # Act
    got = read_state(path)
    # Assert
    assert got is None


def test_read_state_returns_none_for_malformed_json(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    # Act
    got = read_state(path)
    # Assert
    assert got is None


def test_read_state_round_trips_via_atomic_write(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    s = SupervisorState(
        pid=42, started_at=1.0, written_at=2.0, scitex_dev_version="x.y"
    )
    write_state_atomically(s, path)
    # Act
    got = read_state(path)
    # Assert
    assert got is not None and got.pid == 42


def test_read_state_round_trip_preserves_children(tmp_path):
    # Arrange
    path = tmp_path / "state.json"
    s = SupervisorState(children=[{"name": "n", "status": "running"}])
    write_state_atomically(s, path)
    # Act
    got = read_state(path)
    # Assert
    assert got is not None and got.children == [{"name": "n", "status": "running"}]


def test_read_state_permissive_about_missing_fields(tmp_path):
    # Arrange — a stripped-down older snapshot.
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"pid": 7}), encoding="utf-8")
    # Act
    got = read_state(path)
    # Assert
    assert got is not None and got.pid == 7


# EOF
