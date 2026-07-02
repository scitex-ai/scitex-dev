"""Tests for scitex-dev's OWN SystemDepSpec provider (``_system_deps``).

scitex-dev's first self-declaration: ``rsync``, required by the
``scholar-library-sync`` managed cron job (``scitex-ssh sync`` wraps
rsync). Pins the provider contract the entry-point federation expects.
"""

from __future__ import annotations

from scitex_dev._system_deps import provide
from scitex_dev.system_deps import SystemDepSpec


def test_provide_returns_list_of_system_dep_specs():
    # Arrange
    # Act
    deps = provide()
    # Assert
    assert all(isinstance(d, SystemDepSpec) for d in deps)


def test_provide_declares_rsync():
    # Arrange
    # Act
    packages = [d.package for d in provide()]
    # Assert — the scholar-library-sync cron job shells into rsync.
    assert "rsync" in packages


def test_provider_field_names_scitex_dev():
    # Arrange
    # Act
    providers = {d.provider for d in provide()}
    # Assert
    assert providers == {"scitex-dev"}


def test_rsync_needs_no_extra_apt_repo():
    # Arrange
    # Act
    rsync = next(d for d in provide() if d.package == "rsync")
    # Assert — rsync ships in the default repos; apt_repo stays None.
    assert rsync.apt_repo is None
