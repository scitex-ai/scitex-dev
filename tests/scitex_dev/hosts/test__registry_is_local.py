#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Locality is COMPUTED from the running host, never read from the registry.

Reported by dotfiles 2026-08-12 and verified on scitex-compute-04:

    /home/ywatanabe/.scitex/dev/hosts.yaml     Aug  5 12:43
      ywata-note-win:
        ssh_alias: null            <- documented as "the host IS local"
    hostname                                   scitex-compute-04

The registry was authored on the laptop, where that was true. Read anywhere
else the same line asserts that the laptop is this machine, and a consumer
inferring "no SSH hop needed" would run locally with no error, because
"local" is a legitimate answer.

**Locality is not a property of a host. It is a RELATION between a host and
whoever is asking**, so no field in a SHARED registry can carry it: the value
is written from one vantage point and read from many.

Same discipline as `scitex_dev.store`'s node identity, which comes from
`pg_control_system().system_identifier` precisely so a COPIED file cannot lie
about which machine it is on.
"""

from __future__ import annotations

import socket

from scitex_dev.hosts import is_local


def test_this_machine_is_local():
    # Arrange
    here = socket.gethostname()
    # Act
    verdict = is_local(here)
    # Assert
    assert verdict


def test_another_machine_is_not_local():
    """The regression itself: a host that is not this one must read remote,
    whatever the registry happens to record for it."""
    # Arrange
    not_here = "definitely-not-this-host-20260812"
    # Act
    verdict = is_local(not_here)
    # Assert
    assert not verdict


def test_a_fqdn_matches_its_short_name():
    """A registry short name and a FQDN hostname must agree, or every host
    with a domain suffix reads as remote from itself."""
    # Arrange
    short = socket.gethostname().split(".", 1)[0]
    # Act
    verdict = is_local(f"{short}.example.invalid")
    # Assert
    assert verdict


def test_the_comparison_ignores_case():
    # Arrange
    shouted = socket.gethostname().upper()
    # Act
    verdict = is_local(shouted)
    # Assert
    assert verdict


# EOF
