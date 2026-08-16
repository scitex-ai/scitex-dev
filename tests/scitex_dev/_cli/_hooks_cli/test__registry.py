#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/_hooks_cli/test__registry.py

"""Tests for :mod:`scitex_dev._cli._hooks_cli._registry`.

Mirrors the module per PS-204. The existing hook entries are exercised
through the CLI surfaces in ``test___init__.py``; this file covers the
REGISTRY as data -- specifically that a shipped hook is actually reachable
through it, which is the difference between "the file is in the wheel" and
"`hooks install` will deploy it".
"""

from __future__ import annotations

import os

from scitex_dev._cli._hooks_cli._registry import KNOWN_HOOKS

MERGE_GATE = "require_mergeable_verdict"


def test_the_merge_gate_is_registered():
    """Shipping the file is not enough -- `hooks install` reads THIS dict."""
    # Arrange
    registry = KNOWN_HOOKS
    # Act
    present = MERGE_GATE in registry
    # Assert
    assert present


def test_the_merge_gate_source_exists_on_disk():
    """A registry entry pointing at a missing file installs a broken symlink."""
    # Arrange
    source = KNOWN_HOOKS[MERGE_GATE][0]
    # Act
    exists = os.path.isfile(source)
    # Assert
    assert exists


def test_the_merge_gate_deploys_under_pre_tool_use():
    """It gates a TOOL CALL, so it must land where pre-tool-use hooks run."""
    # Arrange
    deploy_rel = KNOWN_HOOKS[MERGE_GATE][1]
    # Act
    parent = os.path.dirname(deploy_rel)
    # Assert
    assert parent.endswith("pre-tool-use")


def test_every_registered_hook_has_an_existing_source():
    """Guards the whole registry, not just the entry added last.

    A registry whose sources are not checked is a list of promises; the
    symlink it creates would be broken and `hooks list` would report
    `stale` for something nobody touched.
    """
    # Arrange
    registry = KNOWN_HOOKS
    # Act
    missing = [n for n, (src, _) in registry.items() if not os.path.isfile(src)]
    # Assert
    assert missing == []


# EOF
