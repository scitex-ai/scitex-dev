#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the skills export system."""

import stat

import pytest

from scitex_dev._core.discovery import invalidate_cache
from scitex_dev._ecosystem._skills.skills import (
    _find_skills_dir,
    _stamp_frontmatter_field,
    export_skills,
    list_skills,
)


def _stamp_manifest_version(content: str, version: str) -> str:
    """Compatibility shim — the legacy MANIFEST.md helper has been
    replaced by the generic `_stamp_frontmatter_field`. Tests that
    exercise the version-stamping behaviour now route through it."""
    return _stamp_frontmatter_field(content, "version", version)


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


# ---------------------------------------------------------------------------
# TestStampManifestVersion
# ---------------------------------------------------------------------------


class TestStampManifestVersion:
    """Tests for _stamp_manifest_version (pure function)."""

    def test_replaces_version_in_frontmatter(self):
        # Arrange
        # Act
        # Assert
        content = "---\npackage: foo\nversion: 0.0.0\n---\n# Body\n"
        result = _stamp_manifest_version(content, "1.2.3")
        assert "version: 1.2.3" in result

    def test_only_replaces_first_occurrence_result_count_version_9_9_9_1(self):
        # Arrange
        # Act
        # Assert
        content = "---\nversion: 0.0.0\n---\n# Body\n\nversion: keep-this\n"
        result = _stamp_manifest_version(content, "9.9.9")
        assert result.count("version: 9.9.9") == 1

    def test_only_replaces_first_occurrence_version_keep_this_in_result(self):
        # Arrange
        # Act
        # Assert
        content = "---\nversion: 0.0.0\n---\n# Body\n\nversion: keep-this\n"
        result = _stamp_manifest_version(content, "9.9.9")
        assert "version: keep-this" in result

    def test_preserves_rest_of_content(self):
        # Arrange
        # Act
        # Assert
        body = "# Manifest\n\nSome important text.\n"
        content = f"---\nversion: 0.0.0\n---\n{body}"
        result = _stamp_manifest_version(content, "2.0.0")
        assert body in result

    def test_inserts_version_field_when_missing_version_1_0_0_in_result(self):
        # The new generic stamper INSERTS the field if it's missing
        # (legacy MANIFEST.md helper used to leave content unchanged).
        # Inserting is the desired behavior for stamping every cached
        # leaf so drift detection works on first export.
        # Arrange
        # Act
        # Assert
        content = "---\npackage: foo\n---\n# No version here\n"
        result = _stamp_manifest_version(content, "1.0.0")
        assert "version: 1.0.0" in result

    def test_inserts_version_field_when_missing_package_foo_in_result(self):
        # The new generic stamper INSERTS the field if it's missing
        # (legacy MANIFEST.md helper used to leave content unchanged).
        # Inserting is the desired behavior for stamping every cached
        # leaf so drift detection works on first export.
        # Arrange
        # Act
        # Assert
        content = "---\npackage: foo\n---\n# No version here\n"
        result = _stamp_manifest_version(content, "1.0.0")
        assert "package: foo" in result

    def test_inserts_version_field_when_missing_no_version_here_in_result(self):
        # The new generic stamper INSERTS the field if it's missing
        # (legacy MANIFEST.md helper used to leave content unchanged).
        # Inserting is the desired behavior for stamping every cached
        # leaf so drift detection works on first export.
        # Arrange
        # Act
        # Assert
        content = "---\npackage: foo\n---\n# No version here\n"
        result = _stamp_manifest_version(content, "1.0.0")
        assert "# No version here" in result

    def test_handles_version_with_extra_whitespace_version_3_0_0_in_result(self):
        # Arrange
        # Act
        # Assert
        content = "---\nversion:   0.0.0  \n---\n# Body\n"
        result = _stamp_manifest_version(content, "3.0.0")
        assert "version:   3.0.0" in result

    def test_handles_version_with_extra_whitespace_0_0_0_not_in_result(self):
        # Arrange
        # Act
        # Assert
        content = "---\nversion:   0.0.0  \n---\n# Body\n"
        result = _stamp_manifest_version(content, "3.0.0")
        assert "0.0.0" not in result


# ---------------------------------------------------------------------------
# TestFindSkillsDir
# ---------------------------------------------------------------------------


class TestFindSkillsDir:
    """Tests for _find_skills_dir resolution chain."""

    def test_new_layout_found_result_is_not_none(self, skills_tree):
        # Arrange
        # Act
        # Assert
        result = _find_skills_dir(
            "test_pkg", "test-pkg", _root_fn=lambda _: skills_tree
        )
        assert result is not None

    def test_new_layout_found_result_skills_tree__skills_test_pkg(self, skills_tree):
        # Arrange
        # Act
        # Assert
        result = _find_skills_dir(
            "test_pkg", "test-pkg", _root_fn=lambda _: skills_tree
        )
        assert result == skills_tree / "_skills" / "test-pkg"

    def test_legacy_layout_found_with_deprecation_warning_result_is_not_none(
        self, legacy_skills_tree
    ):
        # Arrange
        # Act
        # Assert
        import io
        import logging

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.WARNING)
        logger = logging.getLogger("scitex_dev._ecosystem._skills.skills")
        logger.addHandler(handler)
        try:
            result = _find_skills_dir(
                "legacy_pkg",
                "legacy-pkg",
                _root_fn=lambda _: legacy_skills_tree,
            )
        finally:
            logger.removeHandler(handler)

        assert result is not None

    def test_legacy_layout_found_with_deprecation_warning_result_legacy_skills_tree_skills(
        self, legacy_skills_tree
    ):
        # Arrange
        # Act
        # Assert
        import io
        import logging

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.WARNING)
        logger = logging.getLogger("scitex_dev._ecosystem._skills.skills")
        logger.addHandler(handler)
        try:
            result = _find_skills_dir(
                "legacy_pkg",
                "legacy-pkg",
                _root_fn=lambda _: legacy_skills_tree,
            )
        finally:
            logger.removeHandler(handler)

        assert result == legacy_skills_tree / "skills"

    def test_legacy_layout_found_with_deprecation_warning_deprecated_in_log_stream_getvalue_lower(
        self, legacy_skills_tree
    ):
        # Arrange
        # Act
        # Assert
        import io
        import logging

        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.WARNING)
        logger = logging.getLogger("scitex_dev._ecosystem._skills.skills")
        logger.addHandler(handler)
        try:
            result = _find_skills_dir(
                "legacy_pkg",
                "legacy-pkg",
                _root_fn=lambda _: legacy_skills_tree,
            )
        finally:
            logger.removeHandler(handler)

        assert "deprecated" in log_stream.getvalue().lower()

    def test_new_layout_takes_priority_over_legacy(self, tmp_path):
        """When both layouts exist, new layout wins."""
        # Arrange
        # Act
        # Assert
        pkg_root = tmp_path / "pkg_root"
        # Create new layout
        new_dir = pkg_root / "_skills" / "dual-pkg"
        new_dir.mkdir(parents=True)
        (new_dir / "SKILL.md").write_text("# New\n")
        # Create legacy layout
        legacy_dir = pkg_root / "skills"
        legacy_dir.mkdir(parents=True)
        (legacy_dir / "SKILL.md").write_text("# Legacy\n")

        result = _find_skills_dir("dual_pkg", "dual-pkg", _root_fn=lambda _: pkg_root)
        assert result == new_dir

    def test_no_skill_md_returns_none(self, tmp_path):
        """Directory exists but has no SKILL.md."""
        # Arrange
        # Act
        # Assert
        pkg_root = tmp_path / "pkg_root"
        (pkg_root / "_skills" / "empty-pkg").mkdir(parents=True)

        result = _find_skills_dir("empty_pkg", "empty-pkg", _root_fn=lambda _: pkg_root)
        assert result is None

    def test_nonexistent_module_returns_none(self):
        # Arrange
        # Act
        # Assert
        result = _find_skills_dir(
            "no_such_module", "no-such-pkg", _root_fn=lambda _: None
        )
        assert result is None

    def test_docs_master_legacy_layout(self, tmp_path):
        """DEPRECATED docs/MASTER/skills/ layout is still found."""
        # Arrange
        # Act
        # Assert
        pkg_root = tmp_path / "pkg_root"
        docs_dir = pkg_root / "docs" / "MASTER" / "skills"
        docs_dir.mkdir(parents=True)
        (docs_dir / "SKILL.md").write_text("# Docs skills\n")

        result = _find_skills_dir("docs_pkg", "docs-pkg", _root_fn=lambda _: pkg_root)
        assert result == docs_dir


# ---------------------------------------------------------------------------
# TestExportSkills
# ---------------------------------------------------------------------------


def _inject_kwargs(pkg_root, pip_name="test-pkg", module_name="test_pkg"):
    """Return kwargs that pin discovery to a synthetic single-package world."""
    return dict(
        _discover_fn=lambda: {pip_name: module_name},
        _root_fn=lambda _name: pkg_root,
        _version_fn=lambda _pip: "1.0.0",
    )


class TestExportSkills:
    """Tests for export_skills (filesystem operations)."""

    def test_export_copies_files_to_dest_test_pkg_in_exported(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        exported = export_skills(dest, **_inject_kwargs(skills_tree))

        assert "test-pkg" in exported
        pkg_dir = dest / "test-pkg"

    def test_export_copies_files_to_dest_pkg_dir_is_dir(self, tmp_path, skills_tree):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        exported = export_skills(dest, **_inject_kwargs(skills_tree))

        pkg_dir = dest / "test-pkg"
        assert pkg_dir.is_dir()

    def test_export_copies_files_to_dest_pkg_dir_skill_md_exists(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        exported = export_skills(dest, **_inject_kwargs(skills_tree))

        pkg_dir = dest / "test-pkg"
        assert (pkg_dir / "SKILL.md").exists()

    def test_export_copies_files_to_dest_pkg_dir_sub_skill_md_exists(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        exported = export_skills(dest, **_inject_kwargs(skills_tree))

        pkg_dir = dest / "test-pkg"
        assert (pkg_dir / "sub-skill.md").exists()

    def test_export_stamps_manifest_version_version_1_0_0_in_manifest(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        manifest = (dest / "test-pkg" / "MANIFEST.md").read_text()
        assert "version: 1.0.0" in manifest

    def test_export_stamps_manifest_version_version_0_0_0_not_in_manifest(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        manifest = (dest / "test-pkg" / "MANIFEST.md").read_text()
        assert "version: 0.0.0" not in manifest

    def test_export_includes_manifest_in_output(self, tmp_path, skills_tree):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        exported = export_skills(dest, **_inject_kwargs(skills_tree))

        file_names = [f.name for f in exported["test-pkg"]]
        assert "MANIFEST.md" in file_names

    def test_export_flattens_references_path_in_skill_md_references_not_in_skill_content(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        skill_content = (dest / "test-pkg" / "SKILL.md").read_text()
        # references/ prefix should be stripped
        assert "references/" not in skill_content
        # But the link target should remain

    def test_export_flattens_references_path_in_skill_md_sub_skill_md_in_skill_content(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        skill_content = (dest / "test-pkg" / "SKILL.md").read_text()
        # references/ prefix should be stripped
        # But the link target should remain
        assert "sub-skill.md" in skill_content

    def test_clean_removes_stale_files_not_stale_file_exists(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        pkg_dir = dest / "test-pkg"
        pkg_dir.mkdir(parents=True)
        stale_file = pkg_dir / "old-removed-skill.md"
        stale_file.write_text("stale content")

        export_skills(dest, clean=True, **_inject_kwargs(skills_tree))

        # Stale file should be gone after clean=True (rmtree then re-copy)
        assert not stale_file.exists()
        # Fresh files should be present

    def test_clean_removes_stale_files_pkg_dir_skill_md_exists(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        pkg_dir = dest / "test-pkg"
        pkg_dir.mkdir(parents=True)
        stale_file = pkg_dir / "old-removed-skill.md"
        stale_file.write_text("stale content")

        export_skills(dest, clean=True, **_inject_kwargs(skills_tree))

        # Stale file should be gone after clean=True (rmtree then re-copy)
        # Fresh files should be present
        assert (pkg_dir / "SKILL.md").exists()

    def test_overwrite_read_only_file_succeeds(self, tmp_path, skills_tree):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        pkg_dir = dest / "test-pkg"
        pkg_dir.mkdir(parents=True)
        ro_file = pkg_dir / "SKILL.md"
        ro_file.write_text("read-only content")
        ro_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0o444

        # Should not raise PermissionError
        export_skills(dest, **_inject_kwargs(skills_tree))

        # File should now contain the fresh export
        assert "read-only content" not in ro_file.read_text()

    def test_root_skill_md_index_is_generated_root_skill_exists(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        root_skill = dest / "SKILL.md"
        assert root_skill.exists()
        content = root_skill.read_text()

    def test_root_skill_md_index_is_generated_test_pkg_in_content(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        root_skill = dest / "SKILL.md"
        content = root_skill.read_text()
        assert "test-pkg" in content

    def test_root_skill_md_index_is_generated_scitex_in_content(
        self, tmp_path, skills_tree
    ):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "out"
        export_skills(dest, **_inject_kwargs(skills_tree))

        root_skill = dest / "SKILL.md"
        content = root_skill.read_text()
        assert "SciTeX" in content


# ---------------------------------------------------------------------------
# TestSkillsCLI
# ---------------------------------------------------------------------------


class TestSkillsCLI:
    """Lightweight CLI smoke tests — substantive behaviour is exercised in
    ``TestExportSkills`` via direct calls into ``export_skills`` with
    injection hooks. We only verify here that the CLI surface boots and
    accepts the documented flags.
    """

    @pytest.fixture()
    def cli_group(self):
        """Build a minimal click group with skills commands registered."""
        import click
        from scitex_dev._cli.skills._manage import register_skills_commands

        @click.group()
        def cli():
            pass

        register_skills_commands(cli)
        return cli

    def test_export_help_shows_flags_result_exit_code_0(self, cli_group):
        # Arrange
        # Act
        # Assert
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(cli_group, ["skills", "export", "--help"])
        assert result.exit_code == 0

    def test_export_help_shows_flags_dry_run_in_result_output(self, cli_group):
        # Arrange
        # Act
        # Assert
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(cli_group, ["skills", "export", "--help"])
        assert "--dry-run" in result.output

    def test_export_help_shows_flags_dest_in_result_output(self, cli_group):
        # Arrange
        # Act
        # Assert
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(cli_group, ["skills", "export", "--help"])
        assert "--dest" in result.output

    def test_list_help_runs(self, cli_group):
        # Arrange
        # Act
        # Assert
        from click.testing import CliRunner

        runner = CliRunner()
        result = runner.invoke(cli_group, ["skills", "list", "--help"])
        assert result.exit_code == 0


# A second integration-style test that drives the full list_skills surface
# against the synthetic skills_tree fixture, without going through the CLI.


@pytest.fixture
def _injected_list_skills_result(skills_tree):
    # Arrange / Act
    return list_skills(
        _discover_fn=lambda: {"test-pkg": "test_pkg"},
        _root_fn=lambda _: skills_tree,
        _version_fn=lambda _: "9.9.9",
    )


def test_list_skills_injected_result_contains_test_pkg(_injected_list_skills_result):
    # Arrange
    result = _injected_list_skills_result
    # Act
    keys = set(result.keys())
    # Assert
    assert "test-pkg" in keys


def test_list_skills_injected_result_includes_SKILL_entry(_injected_list_skills_result):
    # Arrange
    entries = _injected_list_skills_result["test-pkg"]
    # Act
    names = {e["name"] for e in entries}
    # Assert
    assert "SKILL" in names


def test_list_skills_injected_result_includes_sub_skill_entry(
    _injected_list_skills_result,
):
    # Arrange
    entries = _injected_list_skills_result["test-pkg"]
    # Act
    names = {e["name"] for e in entries}
    # Assert
    assert "sub-skill" in names


def test_list_skills_injected_entries_carry_version(_injected_list_skills_result):
    # Arrange
    entries = _injected_list_skills_result["test-pkg"]
    # Act
    versions = [e["version"] for e in entries]
    # Assert
    assert all(v == "9.9.9" for v in versions)
