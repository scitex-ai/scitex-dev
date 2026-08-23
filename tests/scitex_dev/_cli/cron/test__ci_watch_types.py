#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/cron/test__ci_watch_types.py
"""The ci-watch target map names sac agents; those names must be real."""

from __future__ import annotations

from scitex_dev._cli.cron._ci_watch_types import AGENTS_TO_REPOS

#: The agent names as of the 2026-08-23 migration, verified against sac's
#: registry on compute-04 (140 agents defined; every one of these present).
EXPECTED_AGENTS = {
    "scitex-stats",
    "scitex-types",
    "scitex-dict",
    "scitex-str",
    "scitex-datetime",
}

#: Retired prefix. The fleet renamed `proj-scitex-*` to the bare form and
#: this map was not migrated with it, so ci-watch dispatched to names with
#: no spec.yaml for five days while still correctly finding red CI.
RETIRED_PREFIX = "proj-"


def test_the_map_names_the_agents_that_exist():
    # Arrange
    # Act
    names = set(AGENTS_TO_REPOS)
    # Assert
    assert names == EXPECTED_AGENTS


def test_no_key_uses_the_retired_proj_prefix():
    # Arrange
    # Act
    stale = [k for k in AGENTS_TO_REPOS if k.startswith(RETIRED_PREFIX)]
    # Assert — a dispatch to an undefined name fails loudly at sac and
    # then goes unread; the map is the only place to catch it early
    assert stale == []


def test_every_agent_maps_to_a_repo_path():
    # Arrange
    # Act
    malformed = [r for r in AGENTS_TO_REPOS.values() if r.count("/") != 1]
    # Assert
    assert malformed == []

# EOF
