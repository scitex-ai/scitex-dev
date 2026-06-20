#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for `sync_skills` — idempotent (re-)install with a change report.

No mocks: a synthetic single-package skills tree on ``tmp_path`` is pinned
via the same dependency-injection hooks ``export_skills`` exposes
(``_discover_fn`` / ``_root_fn`` / ``_version_fn``).
"""

from __future__ import annotations

import pytest

from scitex_dev._core.discovery import invalidate_cache
from scitex_dev._ecosystem._skills.skills import sync_skills


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure discovery cache is cleared between tests."""
    # Arrange
    invalidate_cache()
    # Act
    yield
    # Assert
    invalidate_cache()


@pytest.fixture()
def skills_tree(tmp_path):
    """New-layout skills tree: SKILL.md + one sub-skill."""
    # Arrange
    pkg_root = tmp_path / "pkg_root"
    skills_dir = pkg_root / "_skills" / "test-pkg"
    skills_dir.mkdir(parents=True)
    # Act
    (skills_dir / "SKILL.md").write_text(
        "---\nname: test-pkg\ndescription: Test package skills\n---\n# test-pkg\n"
    )
    (skills_dir / "sub-skill.md").write_text(
        "---\ndescription: A sub skill\n---\n# Sub Skill\n"
    )
    # Assert
    return pkg_root


def _inject(pkg_root, version="1.0.0"):
    """Pin discovery to a synthetic single-package world."""
    return dict(
        _discover_fn=lambda: {"test-pkg": "test_pkg"},
        _root_fn=lambda _name: pkg_root,
        _version_fn=lambda _pip: version,
    )


class TestSyncSkillsFirstRun:
    """First sync into an empty destination: everything is `added`."""

    def test_first_sync_reports_changed_true(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert report["changed"] is True

    def test_first_sync_adds_skill_files(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert "test-pkg/SKILL.md" in report["added"]

    def test_first_sync_adds_sub_skill(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert "test-pkg/sub-skill.md" in report["added"]

    def test_first_sync_nothing_updated(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert report["updated"] == []

    def test_first_sync_nothing_removed(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert report["removed"] == []

    def test_first_sync_writes_files_to_disk(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert (dest / "test-pkg" / "SKILL.md").exists()

    def test_first_sync_returns_exported_mapping(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert "test-pkg" in report["exported"]


class TestSyncSkillsIdempotent:
    """Re-running an up-to-date sync is a no-op change-wise."""

    def test_second_sync_reports_changed_false(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert report["changed"] is False

    def test_second_sync_nothing_added(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert report["added"] == []

    def test_second_sync_reports_unchanged_files(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert "test-pkg/SKILL.md" in report["unchanged"]

    def test_second_sync_preserves_file_content(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        first = (dest / "test-pkg" / "SKILL.md").read_text()
        # Act
        sync_skills(dest, **_inject(skills_tree))
        second = (dest / "test-pkg" / "SKILL.md").read_text()
        # Assert
        assert first == second


class TestSyncSkillsDetectsUpdate:
    """A changed source leaf is reported as `updated`, not `added`."""

    def test_source_edit_is_reported_updated(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        (skills_tree / "_skills" / "test-pkg" / "sub-skill.md").write_text(
            "---\ndescription: A sub skill\n---\n# Sub Skill EDITED\n"
        )
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert "test-pkg/sub-skill.md" in report["updated"]

    def test_source_edit_marks_changed_true(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        (skills_tree / "_skills" / "test-pkg" / "sub-skill.md").write_text(
            "# Different body entirely\n"
        )
        # Act
        report = sync_skills(dest, **_inject(skills_tree))
        # Assert
        assert report["changed"] is True

    def test_version_bump_is_reported_updated(self, tmp_path, skills_tree):
        # The per-leaf version stamp changes when the installed version
        # bumps, so a re-sync at a new version reports the leaf as updated.
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree, version="1.0.0"))
        # Act
        report = sync_skills(dest, **_inject(skills_tree, version="2.0.0"))
        # Assert
        assert "test-pkg/sub-skill.md" in report["updated"]


class TestSyncSkillsCleanReportsRemoved:
    """A stale leaf removed by --clean shows up under `removed`."""

    def test_clean_removes_stale_leaf(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        stale = dest / "test-pkg" / "old-removed-skill.md"
        stale.write_text("stale content\n")
        # Act
        report = sync_skills(dest, clean=True, **_inject(skills_tree))
        # Assert
        assert "test-pkg/old-removed-skill.md" in report["removed"]

    def test_clean_marks_changed_true_when_removing(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        (dest / "test-pkg" / "old-removed-skill.md").write_text("stale\n")
        # Act
        report = sync_skills(dest, clean=True, **_inject(skills_tree))
        # Assert
        assert report["changed"] is True

    def test_clean_keeps_real_files(self, tmp_path, skills_tree):
        # Arrange
        dest = tmp_path / "out"
        sync_skills(dest, **_inject(skills_tree))
        (dest / "test-pkg" / "old-removed-skill.md").write_text("stale\n")
        # Act
        sync_skills(dest, clean=True, **_inject(skills_tree))
        # Assert
        assert (dest / "test-pkg" / "SKILL.md").exists()


# EOF
