#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex-dev's own store declarations.

The load-bearing test in this file is
``test_the_builtin_does_not_arrive_through_an_entry_point``. scitex-dev is
a LEAF of this federation, not a privileged parent: it must not register
itself in the group it also reads, or discovery walks this package's own
metadata to find this package.
"""

from __future__ import annotations

from scitex_dev.store import WriterPolicy, discover_store_plugins
from scitex_dev.store.federation._builtin import provide

BUILTIN_NAME = "status_exchanges"


def test_the_builtin_is_declared():
    # Arrange
    # Act
    names = [p.name for p in provide()]
    # Assert
    assert names == [BUILTIN_NAME]


def test_the_builtin_is_found_without_entry_points():
    # Arrange — it must not be conditional on scitex-dev being pip-installed
    # with its .dist-info present: a source checkout on PYTHONPATH would
    # otherwise lose its own store while every leaf kept theirs.
    # Act
    names = [p.name for p in discover_store_plugins(include_entry_points=False)]
    # Assert
    assert names == [BUILTIN_NAME]


def test_include_builtins_false_drops_it():
    # Arrange — the seam that makes exact-list assertions possible.
    # Act
    found = discover_store_plugins(
        include_entry_points=False, include_builtins=False
    )
    # Assert
    assert found == []


def test_the_builtin_does_not_arrive_through_an_entry_point():
    # Arrange — with builtins OFF, the entry-point walk is the ONLY source
    # left. If scitex-dev ever registers itself under its own group, this
    # name reappears here and the self-recursion is back.
    # Act
    names = [
        p.name
        for p in discover_store_plugins(
            include_entry_points=True, include_builtins=False
        )
    ]
    # Assert
    assert BUILTIN_NAME not in names


def test_the_builtin_names_scitex_dev_as_its_provider():
    # Arrange
    # Act
    plugin = provide()[0]
    # Assert
    assert plugin.provider == "scitex-dev"


def test_an_exchange_ledger_is_multi_writer():
    # Arrange — an exchange is written by BOTH ends: the initiator opens it
    # and the responder concludes it. SINGLE_WRITER would reject the
    # completion, which is the half-recorded exchange the ledger exists to
    # make findable.
    # Act
    plugin = provide()[0]
    # Assert
    assert plugin.writer_policy is WriterPolicy.MULTI_WRITER


def test_the_builtin_carries_a_real_schema():
    # Arrange — a federation whose only built-in is a stub proves the seam
    # exists but never that it carries anything.
    # Act
    plugin = provide()[0]
    # Assert
    assert "exchange_id" in plugin.schema.fields

# EOF
