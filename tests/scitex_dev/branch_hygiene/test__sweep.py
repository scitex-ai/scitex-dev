#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The two axes, consumed from the registries rather than re-derived.

These tests pin the CONSUMPTION, not the contents. The package list and
the host list are other modules' facts and change every week; what must
not change is that this sweep reads them from
:mod:`scitex_dev._ecosystem` and :mod:`scitex_dev.hosts` instead of
walking a directory or carrying a hardcoded list of machines.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.branch_hygiene import fleet_hosts, registry_repos
from scitex_dev.branch_hygiene._sweep import remote_argv


def test_the_package_axis_comes_from_the_registry(tmp_path):
    """The registry names the package; the filesystem confirms it is here.

    The registry is passed in rather than patched: it is another
    module's living data, so a test that rewrote it would be asserting
    somebody else's list. What is pinned here is that this module READS
    a registry at all instead of walking ``~/proj``.
    """
    # Arrange
    checkout = tmp_path / "made-up-package"
    (checkout / ".git").mkdir(parents=True)
    # Act
    found = registry_repos(registry={"made-up-package": {"local_path": str(checkout)}})
    # Assert
    assert found == [("made-up-package", Path(checkout))]


def test_a_registered_package_absent_from_this_host_is_skipped(tmp_path):
    """A package registered fleet-wide but not checked out here is not
    this host's business, and must not read as an error."""
    # Arrange
    absent = {"never-cloned": {"local_path": str(tmp_path / "never-cloned")}}
    # Act
    found = registry_repos(registry=absent)
    # Assert
    assert found == []


def test_an_archived_package_is_not_swept(tmp_path):
    """Archived is the registry's own way of saying "not ours any more"."""
    # Arrange
    checkout = tmp_path / "retired-package"
    (checkout / ".git").mkdir(parents=True)
    entry = {"local_path": str(checkout), "archived": True}
    # Act
    found = registry_repos(registry={"retired-package": entry})
    # Assert
    assert found == []


def test_the_host_axis_comes_from_the_host_registry():
    """Every visited alias must be one the registry named. The registry
    is allowed to be empty on a given machine; a hardcoded list is not
    allowed to exist at all."""
    # Arrange
    from scitex_dev.hosts import list_hosts

    known = {host.ssh_alias for host in list_hosts() if host.ssh_alias}
    # Act
    aliases, _ = fleet_hosts()
    # Assert
    assert set(aliases) <= known


def test_every_host_the_fan_out_declines_says_why():
    """A fan-out that silently visits four of nine hosts reports the
    same 'all clean' as one that visited all nine."""
    # Arrange
    # Act
    _, skipped = fleet_hosts()
    # Assert
    assert all(reason for _, reason in skipped)


def test_the_fan_out_never_asks_a_remote_host_for_the_remote_leg():
    """Structural, not a convention: the remote refspace is shared, so
    one pass serves the fleet and the rest are redundant failures."""
    # Arrange
    # Act
    argv = remote_argv(execute=True, max_age_hours=24.0, packages=None)
    # Assert
    assert "--no-remote" in argv


def test_the_fan_out_forwards_the_execute_decision():
    """A dry run that quietly becomes a real run on six other machines
    is the worst possible shape for this verb."""
    # Arrange
    # Act
    argv = remote_argv(execute=False, max_age_hours=24.0, packages=None)
    # Assert
    assert "--execute" not in argv


# EOF
