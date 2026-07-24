#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the ecosystem package registry (scitex_dev._ecosystem._registry).

Pins the invariants of the two-part table split (the 512-line file cap
forced ``ECOSYSTEM`` into ``_registry_data_1`` / ``_registry_data_2``):
the public surface is unchanged, the parts are disjoint and merged in
display order, and every ``github_repo`` value is a well-formed
``owner/repo`` slug (post ywatanabe1989 -> scitex-ai org migration).
No network access — GitHub truth was verified out-of-band via
``gh api repos/<owner>/<repo> --jq .full_name`` (which follows renames).
"""

from __future__ import annotations

import re

import pytest

from scitex_dev._ecosystem._registry import ECOSYSTEM, PackageInfo
from scitex_dev._ecosystem._registry_data_1 import ECOSYSTEM_PART_1
from scitex_dev._ecosystem._registry_data_2 import ECOSYSTEM_PART_2

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def test_registry_module_still_exposes_ecosystem():
    # Arrange
    from scitex_dev._ecosystem import _registry

    # Act
    exposed = _registry.ECOSYSTEM
    # Assert
    assert exposed is ECOSYSTEM


def test_core_reexport_still_resolves_to_same_ecosystem():
    # Arrange
    from scitex_dev._ecosystem._core import ECOSYSTEM as core_eco

    # Act
    same = core_eco is ECOSYSTEM
    # Assert
    assert same


def test_registry_module_still_exposes_package_info():
    # Arrange
    from scitex_dev._ecosystem import _registry

    # Act
    exposed = _registry.PackageInfo
    # Assert
    assert exposed is PackageInfo


def test_registry_all_is_unchanged_after_split():
    # Arrange
    from scitex_dev._ecosystem import _registry

    # Act
    public = _registry.__all__
    # Assert
    assert public == ["ECOSYSTEM", "PackageInfo"]


def test_part_key_sets_are_disjoint():
    # Arrange — a key collision would silently drop an entry in the
    # {**part1, **part2} merge.
    # Act
    overlap = set(ECOSYSTEM_PART_1) & set(ECOSYSTEM_PART_2)
    # Assert
    assert not overlap


def test_merge_preserves_display_order_part1_then_part2():
    # Arrange
    expected = list(ECOSYSTEM_PART_1) + list(ECOSYSTEM_PART_2)
    # Act
    merged_order = list(ECOSYSTEM)
    # Assert
    assert merged_order == expected


@pytest.mark.parametrize("name", sorted(ECOSYSTEM))
def test_entry_has_wellformed_github_repo_slug(name):
    # Arrange
    info = ECOSYSTEM[name]
    # Act
    repo = info.get("github_repo", "")
    # Assert
    assert _OWNER_REPO_RE.match(repo), f"{name}: bad github_repo {repo!r}"


def test_scitex_dev_entry_points_at_scitex_ai_org():
    # Arrange — the audit-footer issues URL is derived from this entry.
    info = ECOSYSTEM["scitex-dev"]
    # Act
    repo = info["github_repo"]
    # Assert
    assert repo == "scitex-ai/scitex-dev"


def test_only_unmigrated_archives_remain_under_ywatanabe1989():
    # Arrange — gh api confirmed (2026-07-21) these two GitHub archives
    # were NOT transferred to the scitex-ai org; everything else was.
    expected_stay = {"scitex-audit", "scitex-bridge"}
    # Act
    stayed = {
        name
        for name, info in ECOSYSTEM.items()
        if info["github_repo"].startswith("ywatanabe1989/")
    }
    # Assert
    assert stayed == expected_stay
