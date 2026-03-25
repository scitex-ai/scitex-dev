#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the skills export system."""

import os
import stat
from unittest.mock import patch

import pytest

from scitex_dev._discovery import invalidate_cache
from scitex_dev.skills import (
    _find_skills_dir,
    _stamp_manifest_version,
    export_skills,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure discovery cache is cleared between tests."""
    invalidate_cache()
    yield
    invalidate_cache()


@pytest.fixture()
def skills_tree(tmp_path):
    """New-layout skills tree with SKILL.md, MANIFEST.md, and sub-skill.md."""
    pkg_root = tmp_path / "pkg_root"
    skills_dir = pkg_root / "_skills" / "test-pkg"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: test-pkg\ndescription: Test package skills\n---\n"
        "# test-pkg Skills\n\n"
        "- [sub-skill](references/sub-skill.md)\n"
    )
    (skills_dir / "MANIFEST.md").write_text(
        "---\n"
        "package: test-pkg\n"
        "version: 0.0.0\n"
        "source: github.com/test/test-pkg\n"
        "---\n"
        "# Skills Manifest\n"
    )
    (skills_dir / "sub-skill.md").write_text(
        "---\ndescription: A sub skill\n---\n# Sub Skill\n"
    )
    return pkg_root


@pytest.fixture()
def legacy_skills_tree(tmp_path):
    """Legacy-layout skills tree with skills/ and references/."""
    pkg_root = tmp_path / "pkg_root"
    skills_dir = pkg_root / "skills"
    refs_dir = skills_dir / "references"
    refs_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: legacy-pkg\ndescription: Legacy skills\n---\n"
        "# Legacy Skills\n\n"
        "- [ref-skill](references/ref-skill.md)\n"
    )
    (refs_dir / "ref-skill.md").write_text(
        "---\ndescription: A reference skill\n---\n# Ref Skill\n"
    )
    return pkg_root


def _mock_discover(pip_name, module_name):
    """Return a mock discover_packages dict for a single package."""
    return {pip_name: module_name}


# ---------------------------------------------------------------------------
# TestStampManifestVersion
# ---------------------------------------------------------------------------


class TestStampManifestVersion:
    """Tests for _stamp_manifest_version (pure function)."""

    def test_replaces_version_in_frontmatter(self):
        content = "---\npackage: foo\nversion: 0.0.0\n---\n# Body\n"
        result = _stamp_manifest_version(content, "1.2.3")
        assert "version: 1.2.3" in result

    def test_only_replaces_first_occurrence(self):
        content = "---\nversion: 0.0.0\n---\n# Body\n\nversion: keep-this\n"
        result = _stamp_manifest_version(content, "9.9.9")
        assert result.count("version: 9.9.9") == 1
        assert "version: keep-this" in result

    def test_preserves_rest_of_content(self):
        body = "# Manifest\n\nSome important text.\n"
        content = f"---\nversion: 0.0.0\n---\n{body}"
        result = _stamp_manifest_version(content, "2.0.0")
        assert body in result

    def test_handles_no_version_field(self):
        content = "---\npackage: foo\n---\n# No version here\n"
        result = _stamp_manifest_version(content, "1.0.0")
        # Content should be unchanged when there is no version: line
        assert result == content

    def test_handles_version_with_extra_whitespace(self):
        content = "---\nversion:   0.0.0  \n---\n# Body\n"
        result = _stamp_manifest_version(content, "3.0.0")
        assert "version:   3.0.0" in result
        assert "0.0.0" not in result


# ---------------------------------------------------------------------------
# TestFindSkillsDir
# ---------------------------------------------------------------------------


class TestFindSkillsDir:
    """Tests for _find_skills_dir resolution chain."""

    def test_new_layout_found(self, skills_tree):
        with patch(
            "scitex_dev.skills.get_package_root",
            return_value=skills_tree,
        ):
            result = _find_skills_dir("test_pkg", "test-pkg")
        assert result is not None
        assert result == skills_tree / "_skills" / "test-pkg"

    def test_legacy_layout_found_with_deprecation_warning(self, legacy_skills_tree):
        with patch(
            "scitex_dev.skills.get_package_root",
            return_value=legacy_skills_tree,
        ):
            import io
            import logging

            log_stream = io.StringIO()
            handler = logging.StreamHandler(log_stream)
            handler.setLevel(logging.WARNING)
            logger = logging.getLogger("scitex_dev.skills")
            logger.addHandler(handler)
            try:
                result = _find_skills_dir("legacy_pkg", "legacy-pkg")
            finally:
                logger.removeHandler(handler)

        assert result is not None
        assert result == legacy_skills_tree / "skills"
        assert "deprecated" in log_stream.getvalue().lower()

    def test_new_layout_takes_priority_over_legacy(self, tmp_path):
        """When both layouts exist, new layout wins."""
        pkg_root = tmp_path / "pkg_root"
        # Create new layout
        new_dir = pkg_root / "_skills" / "dual-pkg"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("# New\n")
        # Create legacy layout
        legacy_dir = pkg_root / "skills"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "SKILL.md").write_text("# Legacy\n")

        with patch(
            "scitex_dev.skills.get_package_root",
            return_value=pkg_root,
        ):
            result = _find_skills_dir("dual_pkg", "dual-pkg")

        assert result == new_dir

    def test_no_skill_md_returns_none(self, tmp_path):
        """Directory exists but has no SKILL.md."""
        pkg_root = tmp_path / "pkg_root"
        (pkg_root / "_skills" / "empty-pkg").mkdir(parents=True)

        with patch(
            "scitex_dev.skills.get_package_root",
            return_value=pkg_root,
        ):
            result = _find_skills_dir("empty_pkg", "empty-pkg")

        assert result is None

    def test_nonexistent_module_returns_none(self):
        with patch(
            "scitex_dev.skills.get_package_root",
            return_value=None,
        ):
            result = _find_skills_dir("no_such_module", "no-such-pkg")

        assert result is None

    def test_docs_master_legacy_layout(self, tmp_path):
        """DEPRECATED docs/MASTER/skills/ layout is still found."""
        pkg_root = tmp_path / "pkg_root"
        docs_dir = pkg_root / "docs" / "MASTER" / "skills"
        docs_dir.mkdir(parents=True)
        (docs_dir / "SKILL.md").write_text("# Docs skills\n")

        with patch(
            "scitex_dev.skills.get_package_root",
            return_value=pkg_root,
        ):
            result = _find_skills_dir("docs_pkg", "docs-pkg")

        assert result == docs_dir


# ---------------------------------------------------------------------------
# TestExportSkills
# ---------------------------------------------------------------------------


class TestExportSkills:
    """Tests for export_skills (filesystem operations)."""

    def _patch_discovery(self, pkg_root, pip_name="test-pkg", module_name="test_pkg"):
        """Return context managers that mock discovery to point at pkg_root."""
        return (
            patch(
                "scitex_dev.skills.discover_packages",
                return_value=_mock_discover(pip_name, module_name),
            ),
            patch(
                "scitex_dev.skills.get_package_root",
                return_value=pkg_root,
            ),
            patch(
                "scitex_dev.skills._get_package_version",
                return_value="1.0.0",
            ),
        )

    def test_export_copies_files_to_dest(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            exported = export_skills(dest=dest, mode="export")

        assert "test-pkg" in exported
        pkg_dir = dest / "scitex" / "test-pkg"
        assert pkg_dir.is_dir()
        assert (pkg_dir / "SKILL.md").exists()
        assert (pkg_dir / "sub-skill.md").exists()

    def test_export_stamps_manifest_version(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            export_skills(dest=dest, mode="export")

        manifest = (dest / "scitex" / "test-pkg" / "MANIFEST.md").read_text()
        assert "version: 1.0.0" in manifest
        assert "version: 0.0.0" not in manifest

    def test_export_includes_manifest_in_output(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            exported = export_skills(dest=dest, mode="export")

        file_names = [f.name for f in exported["test-pkg"]]
        assert "MANIFEST.md" in file_names

    def test_export_flattens_references_path_in_skill_md(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            export_skills(dest=dest, mode="export")

        skill_content = (dest / "scitex" / "test-pkg" / "SKILL.md").read_text()
        # references/ prefix should be stripped
        assert "references/" not in skill_content
        # But the link target should remain
        assert "sub-skill.md" in skill_content

    def test_update_skips_newer_dest_files(self, tmp_path, skills_tree):
        dest = tmp_path / "out" / "scitex" / "test-pkg"
        dest.mkdir(parents=True)
        out_file = dest / "sub-skill.md"
        out_file.write_text("local edit")

        # Make dest file newer than source using os.utime
        src_file = skills_tree / "_skills" / "test-pkg" / "sub-skill.md"
        old_time = 1000000.0
        new_time = 2000000.0
        os.utime(src_file, (old_time, old_time))
        os.utime(out_file, (new_time, new_time))

        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            export_skills(dest=tmp_path / "out", mode="update")

        # Local edit should be preserved because dest is newer
        assert out_file.read_text() == "local edit"

    def test_upgrade_removes_then_copies(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        pkg_dir = dest / "scitex" / "test-pkg"
        pkg_dir.mkdir(parents=True)
        stale_file = pkg_dir / "old-removed-skill.md"
        stale_file.write_text("stale content")

        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            export_skills(dest=dest, mode="upgrade")

        # Stale file should be gone after upgrade (rmtree then re-copy)
        assert not stale_file.exists()
        # Fresh files should be present
        assert (pkg_dir / "SKILL.md").exists()

    def test_overwrite_read_only_file_succeeds(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        pkg_dir = dest / "scitex" / "test-pkg"
        pkg_dir.mkdir(parents=True)
        ro_file = pkg_dir / "SKILL.md"
        ro_file.write_text("read-only content")
        ro_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444

        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            # Should not raise PermissionError
            export_skills(dest=dest, mode="export")

        # File should now contain the fresh export
        assert "read-only content" not in ro_file.read_text()

    def test_root_skill_md_index_is_generated(self, tmp_path, skills_tree):
        dest = tmp_path / "out"
        p1, p2, p3 = self._patch_discovery(skills_tree)
        with p1, p2, p3:
            export_skills(dest=dest, mode="export")

        root_skill = dest / "scitex" / "SKILL.md"
        assert root_skill.exists()
        content = root_skill.read_text()
        assert "test-pkg" in content
        assert "SciTeX" in content


# ---------------------------------------------------------------------------
# TestSkillsCLI
# ---------------------------------------------------------------------------


class TestSkillsCLI:
    """Tests for CLI commands using click.testing.CliRunner."""

    @pytest.fixture()
    def cli_group(self):
        """Build a minimal click group with skills commands registered."""
        import click
        from scitex_dev._cli_skills import register_skills_commands

        @click.group()
        def cli():
            pass

        register_skills_commands(cli)
        return cli

    def _patch_list_skills(self):
        """Mock list_skills to return a small predictable result."""
        return patch(
            "scitex_dev.skills.list_skills",
            return_value={
                "mock-pkg": [
                    {
                        "name": "SKILL",
                        "path": "/fake/SKILL.md",
                        "description": "Mock",
                        "version": "0.1.0",
                    },
                ]
            },
        )

    def test_export_dry_run_prints_plan_writes_no_files(self, cli_group, tmp_path):
        from click.testing import CliRunner

        runner = CliRunner()
        dest = tmp_path / "dry"
        with self._patch_list_skills():
            result = runner.invoke(
                cli_group,
                ["skills", "export", "--dry-run", "--dest", str(dest)],
            )
        assert result.exit_code == 0
        assert "mock-pkg" in result.output
        # No files should have been written
        assert not dest.exists() or not any(dest.rglob("*.md"))

    def test_update_dry_run_writes_nothing(self, cli_group, tmp_path):
        from click.testing import CliRunner

        runner = CliRunner()
        dest = tmp_path / "dry"
        with self._patch_list_skills():
            result = runner.invoke(
                cli_group,
                ["skills", "update", "--dry-run", "--dest", str(dest)],
            )
        assert result.exit_code == 0
        assert not dest.exists() or not any(dest.rglob("*.md"))

    def test_upgrade_dry_run_writes_nothing(self, cli_group, tmp_path):
        from click.testing import CliRunner

        runner = CliRunner()
        dest = tmp_path / "dry"
        with self._patch_list_skills():
            result = runner.invoke(
                cli_group,
                ["skills", "upgrade", "--dry-run", "--dest", str(dest)],
            )
        assert result.exit_code == 0
        assert not dest.exists() or not any(dest.rglob("*.md"))

    def test_export_writes_files(self, cli_group, tmp_path, skills_tree):
        from click.testing import CliRunner

        runner = CliRunner()
        dest = tmp_path / "real"
        with (
            patch(
                "scitex_dev.skills.discover_packages",
                return_value=_mock_discover("test-pkg", "test_pkg"),
            ),
            patch(
                "scitex_dev.skills.get_package_root",
                return_value=skills_tree,
            ),
            patch(
                "scitex_dev.skills._get_package_version",
                return_value="1.0.0",
            ),
        ):
            result = runner.invoke(
                cli_group,
                ["skills", "export", "--dest", str(dest)],
            )
        assert result.exit_code == 0
        assert (dest / "scitex" / "test-pkg" / "SKILL.md").exists()
