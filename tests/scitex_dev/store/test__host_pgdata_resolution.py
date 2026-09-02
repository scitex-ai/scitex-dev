#!/usr/bin/env python3
"""Which PGDATA directory a host resolves to, during and after the move.

The store moved from ``~/.scitex/pg`` to ``~/.scitex/dev/store`` on
2026-09-02. The legacy path stays READABLE so the fleet can move one
machine at a time, and these tests pin the order that makes that safe.

THE CASE THAT MOTIVATES THE WHOLE FILE is
``test_an_empty_new_directory_does_not_win_over_a_live_legacy_cluster``.
An earlier draft asked ``directory.exists()``, which loses to anything
that creates the new path before the data moves — a config writer, a
``mkdir -p`` in a job, someone preparing a rehearsal. The resolver would
then hand every client an EMPTY directory while the live cluster sat at
the legacy path: a cluster nobody is writing to. Caught in review by
scitex-agent-container before it shipped.

NO MOCKS and no ``monkeypatch``: each test builds REAL directories under
``tmp_path`` and injects them, because the behaviour under test is what
the function does with a real filesystem in a particular state. The
resolver takes the two paths as parameters for exactly this reason — a
test that rewrites production constants is testing the rewrite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.store._host import _holds_a_cluster, resolve_pgdata_dir


def _make_cluster(directory: Path) -> Path:
    """A directory PostgreSQL would recognise: PG_VERSION is the marker."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "PG_VERSION").write_text("18\n", encoding="utf-8")
    return directory


@pytest.fixture
def new_dir(tmp_path) -> Path:
    return tmp_path / "dev" / "store"


@pytest.fixture
def legacy_dir(tmp_path) -> Path:
    return tmp_path / "pg"


class TestAMovedHostNeverLooksBack:
    def test_the_new_location_wins_when_it_holds_a_cluster(
        self, new_dir, legacy_dir
    ):
        # Arrange — both hold clusters, which is the state DURING a move.
        _make_cluster(new_dir)
        _make_cluster(legacy_dir)

        # Act
        resolved = resolve_pgdata_dir(new=new_dir, legacy=legacy_dir)

        # Assert — the new location must win, or a moved host would keep
        # reading the data it just migrated away from.
        assert resolved == new_dir


class TestAnUnmovedHostKeepsWorking:
    def test_the_legacy_location_is_used_when_only_it_holds_a_cluster(
        self, new_dir, legacy_dir
    ):
        # Arrange
        _make_cluster(legacy_dir)

        # Act
        resolved = resolve_pgdata_dir(new=new_dir, legacy=legacy_dir)

        # Assert — this is what lets the fleet move one machine at a time
        # rather than needing every host converted before the release lands.
        assert resolved == legacy_dir


class TestTheEmptyDirectoryTrap:
    """The review catch. An empty new path must not beat a live old one."""

    def test_an_empty_new_directory_does_not_win_over_a_live_legacy_cluster(
        self, new_dir, legacy_dir
    ):
        # Arrange — the new path EXISTS but holds no cluster, which is what
        # any `mkdir -p` produces before the data has moved.
        new_dir.mkdir(parents=True, exist_ok=True)
        _make_cluster(legacy_dir)

        # Act
        resolved = resolve_pgdata_dir(new=new_dir, legacy=legacy_dir)

        # Assert — resolving to the new path here would hand every client an
        # empty directory while the live cluster sat at the legacy one.
        assert resolved == legacy_dir

    def test_a_bare_directory_is_not_a_cluster(self, new_dir):
        # Arrange
        new_dir.mkdir(parents=True, exist_ok=True)

        # Act
        holds = _holds_a_cluster(new_dir)

        # Assert — PG_VERSION is the marker because PostgreSQL writes it and
        # refuses to start without it, so it answers "is there a cluster
        # here" rather than "did someone make this folder".
        assert holds is False


class TestAFreshHostIsCreatedInTheRightPlace:
    def test_neither_present_resolves_to_the_new_location(
        self, new_dir, legacy_dir
    ):
        # Arrange — a clean machine: the fixtures name paths under tmp_path
        # and neither is created, so no cluster exists anywhere.

        # Act
        resolved = resolve_pgdata_dir(new=new_dir, legacy=legacy_dir)

        # Assert — the tie must break toward the future, or a brand-new host
        # reintroduces the path this move exists to retire.
        assert resolved == new_dir
