#!/usr/bin/env python3
# Timestamp: 2026-03-09
# File: tests/scitex/_dev/test__rename.py

"""Comprehensive tests for scitex_dev.rename bulk rename utility."""

import os
from pathlib import Path


from scitex_dev.rename import (
    RenameConfig,
    RenameResult,
    bulk_rename,
    execute_rename,
    preview_rename,
)
from scitex_dev.rename.filters import (
    find_matching_files,
    is_django_protected_line,
    is_src_excluded,
    matches_include_extensions,
    parse_csv_config,
    should_exclude_path,
)
from scitex_dev.rename.io import (
    mkdir,
    rename_path,
    rmdir,
    set_sudo_password,
    symlink_to,
    unlink_path,
    write_text,
)
from scitex_dev.rename.safety import (
    check_directory_safety,
    create_backup,
    has_uncommitted_changes,
    is_git_repo,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_execute(pattern, replacement, directory, **kwargs):
    """Execute rename with safety checks bypassed via injection seams.

    We pass synthetic ``uncommitted_check_fn`` / ``safety_check_fn`` so the
    test does not need a real git repo or pass the system-directory guard.
    """
    return execute_rename(
        pattern,
        replacement,
        directory=str(directory),
        uncommitted_check_fn=lambda _dir: False,
        safety_check_fn=lambda _dir: None,
        **kwargs,
    )


# ===========================================================================
# RenameConfig
# ===========================================================================


class TestRenameConfig:
    def test_defaults_match_documented_safe_values_config_dry_run_is_true(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="old", replacement="new")
        assert config.dry_run is True

    def test_defaults_match_documented_safe_values_config_django_safe_is_true(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="old", replacement="new")
        assert config.django_safe is True

    def test_defaults_match_documented_safe_values_config_create_backup_is_false(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="old", replacement="new")
        assert config.create_backup is False

    def test_defaults_match_documented_safe_values_py_in_config_path_includes(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="old", replacement="new")
        assert "py" in config.path_includes

    def test_defaults_match_documented_safe_values_pycache___in_config_path_excludes(
        self,
    ):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="old", replacement="new")
        assert "__pycache__" in config.path_excludes

    def test_custom_values_override_defaults_config_dry_run_is_false(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(
            pattern="foo",
            replacement="bar",
            directory="/tmp",
            dry_run=False,
            django_safe=False,
            extra_excludes=["*.log"],
        )
        assert config.dry_run is False

    def test_custom_values_override_defaults_config_django_safe_is_false(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(
            pattern="foo",
            replacement="bar",
            directory="/tmp",
            dry_run=False,
            django_safe=False,
            extra_excludes=["*.log"],
        )
        assert config.django_safe is False

    def test_custom_values_override_defaults_config_extra_excludes_log(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(
            pattern="foo",
            replacement="bar",
            directory="/tmp",
            dry_run=False,
            django_safe=False,
            extra_excludes=["*.log"],
        )
        assert config.extra_excludes == ["*.log"]

    def test_skip_ids_default_empty(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert config.skip_ids == []

    def test_use_sudo_default_false(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert config.use_sudo is False


# ===========================================================================
# RenameResult
# ===========================================================================


class TestRenameResult:
    def test_error_field_default_none_result_error_is_none(self):
        # Arrange
        # Act
        # Assert
        result = RenameResult(
            dry_run=True,
            pattern="a",
            replacement="b",
            directory=".",
            contents=[],
            symlink_targets=[],
            symlink_names=[],
            file_names=[],
            dir_names=[],
            summary={},
        )
        assert result.error is None

    def test_error_field_default_none_result_collisions(self):
        # Arrange
        # Act
        # Assert
        result = RenameResult(
            dry_run=True,
            pattern="a",
            replacement="b",
            directory=".",
            contents=[],
            symlink_targets=[],
            symlink_names=[],
            file_names=[],
            dir_names=[],
            summary={},
        )
        assert result.collisions == []

    def test_error_field_set(self):
        # Arrange
        # Act
        # Assert
        result = RenameResult(
            dry_run=False,
            pattern="a",
            replacement="b",
            directory=".",
            contents=[],
            symlink_targets=[],
            symlink_names=[],
            file_names=[],
            dir_names=[],
            summary={},
            error="Something went wrong",
        )
        assert result.error == "Something went wrong"


# ===========================================================================
# Filtering
# ===========================================================================


class TestFiltering:
    def test_parse_csv_config_parse_csv_config_py_txt_sh_py_txt_sh(self):
        # Arrange
        # Act
        # Assert
        assert parse_csv_config("py,txt,sh") == ["py", "txt", "sh"]

    def test_parse_csv_config_parse_csv_config(self):
        # Arrange
        # Act
        # Assert
        assert parse_csv_config("") == []

    def test_parse_csv_config_parse_csv_config_py_txt_py_txt(self):
        # Arrange
        # Act
        # Assert
        assert parse_csv_config("  py , txt ") == ["py", "txt"]

    def test_should_exclude_path_pycache(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        path = Path("/some/dir/__pycache__/module.pyc")
        assert should_exclude_path(path, config) is True

    def test_should_exclude_path_normal(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        path = Path("/some/dir/src/module.py")
        assert should_exclude_path(path, config) is False

    def test_should_exclude_path_extra(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y", extra_excludes=["vendor"])
        path = Path("/some/vendor/lib.py")
        assert should_exclude_path(path, config) is True

    def test_should_exclude_path_node_modules(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        path = Path("/project/node_modules/pkg/index.js")
        assert should_exclude_path(path, config) is True

    def test_should_exclude_path_git(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        path = Path("/project/.git/config")
        assert should_exclude_path(path, config) is True

    def test_should_exclude_path_venv(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        path = Path("/project/.venv/lib/site-packages/pkg.py")
        assert should_exclude_path(path, config) is True

    def test_should_exclude_migrations(self):
        """Migrations are in path_must_excludes by default."""
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        path = Path("/project/apps/my_app/migrations/0001_initial.py")
        assert should_exclude_path(path, config) is True

    def test_matches_include_extensions_matches_include_extensions_path_file_py(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert matches_include_extensions(Path("file.py"), config) is True

    def test_matches_include_extensions_matches_include_extensions_path_file_txt(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert matches_include_extensions(Path("file.txt"), config) is True

    def test_matches_include_extensions_matches_include_extensions_path_file_jpg(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert matches_include_extensions(Path("file.jpg"), config) is False

    def test_matches_include_html(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert matches_include_extensions(Path("template.html"), config) is True

    def test_matches_include_ts_matches_include_extensions_path_app_ts_c(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert matches_include_extensions(Path("app.ts"), config) is True

    def test_matches_include_ts_matches_include_extensions_path_comp_tsx(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert matches_include_extensions(Path("comp.tsx"), config) is True

    def test_matches_include_custom_matches_include_extensions_path_main_rs(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y", path_includes="rs,go")
        assert matches_include_extensions(Path("main.rs"), config) is True

    def test_matches_include_custom_matches_include_extensions_path_main_go(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y", path_includes="rs,go")
        assert matches_include_extensions(Path("main.go"), config) is True

    def test_matches_include_custom_matches_include_extensions_path_main_py(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y", path_includes="rs,go")
        assert matches_include_extensions(Path("main.py"), config) is False

    def test_is_django_protected_line_is_django_protected_line_db_table_my_tab(self):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("    db_table = 'my_table'", "my") is True

    def test_is_django_protected_line_is_django_protected_line_related_name_it(self):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("    related_name='items'", "items") is True

    def test_is_django_protected_line_is_django_protected_line_installed_apps(self):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("INSTALLED_APPS = [", "APP") is True

    def test_is_django_protected_line_is_django_protected_line_x_my_function_m(self):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("x = my_function()", "my") is False

    def test_django_protected_does_not_block_app_config_is_django_protected_line_name_apps_modul(
        self,
    ):
        """apps.py name and urls.py app_name should NOT be protected."""
        # Arrange
        # Act
        # Assert
        assert (
            is_django_protected_line('    name = "apps.modulemaker_app"', "modulemaker")
            is False
        )

    def test_django_protected_does_not_block_app_config_is_django_protected_line_app_name_module(
        self,
    ):
        """apps.py name and urls.py app_name should NOT be protected."""
        # Arrange
        # Act
        # Assert
        assert (
            is_django_protected_line('app_name = "modulemaker"', "modulemaker") is False
        )

    def test_django_protected_db_table_still_protected(self):
        # Arrange
        # Act
        # Assert
        assert (
            is_django_protected_line("    db_table = 'old_table'", "old_table") is True
        )

    def test_django_protected_related_name_variants_is_django_protected_line_related_name_ol(
        self,
    ):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("    related_name='old_items'", "old") is True

    def test_django_protected_related_name_variants_is_django_protected_line_related_name_ol_2(
        self,
    ):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line('    related_name="old_items"', "old") is True

    def test_django_protected_manager_line(self):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("    objects = OldManager()", "Old") is True

    def test_django_protected_settings_patterns_is_django_protected_line_databases_data(
        self,
    ):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("DATABASES = {", "DATA") is True

    def test_django_protected_settings_patterns_is_django_protected_line_middleware_mid(
        self,
    ):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("MIDDLEWARE = [", "MID") is True

    def test_django_protected_settings_patterns_is_django_protected_line_templates_temp(
        self,
    ):
        # Arrange
        # Act
        # Assert
        assert is_django_protected_line("TEMPLATES = [", "TEMP") is True

    def test_is_src_excluded_is_src_excluded_db_table_test_config_is(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert is_src_excluded("db_table='test'", config) is True

    def test_is_src_excluded_is_src_excluded_normal_code_here_config(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert is_src_excluded("normal code here", config) is False

    def test_is_src_excluded_related_name(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y")
        assert is_src_excluded("related_name='items'", config) is True

    def test_is_src_excluded_custom(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(
            pattern="x", replacement="y", src_must_excludes="KEEP_THIS"
        )
        assert is_src_excluded("KEEP_THIS = True", config) is True


# ===========================================================================
# Preview rename (dry run)
# ===========================================================================


class TestPreviewRename:
    def test_preview_file_contents_result_dry_run_is_true(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        assert result.dry_run is True

    def test_preview_file_contents_len_result_contents_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        assert len(result.contents) == 1

    def test_preview_file_contents_result_contents_0_matches_2(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        assert result.contents[0]["matches"] == 2

    def test_preview_file_contents_old_name_in_tmp_path_test_py_read_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        assert "old_name" in (tmp_path / "test.py").read_text()

    def test_preview_includes_line_details_lines_in_result_contents_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nkeep\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        assert "lines" in result.contents[0]
        lines = result.contents[0]["lines"]

    def test_preview_includes_line_details_len_lines_2(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nkeep\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert len(lines) == 2

    def test_preview_includes_line_details_lines_0_action_replace(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nkeep\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert lines[0]["action"] == "replace"

    def test_preview_includes_line_details_lines_0_line_num_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nkeep\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert lines[0]["line_num"] == 1

    def test_preview_includes_line_details_old_name_in_lines_0_before(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nkeep\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert "old_name" in lines[0]["before"]

    def test_preview_includes_line_details_new_name_in_lines_0_after(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nkeep\nold_name = 2\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert "new_name" in lines[0]["after"]

    def test_preview_line_details_shows_protected_protect_in_actions(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "db_table = 'old_val'\nold_val = 1\n"
        (tmp_path / "models.py").write_text(content)
        result = preview_rename("old_val", "new_val", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        actions = [l["action"] for l in lines]
        assert "protect" in actions

    def test_preview_line_details_shows_protected_replace_in_actions(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "db_table = 'old_val'\nold_val = 1\n"
        (tmp_path / "models.py").write_text(content)
        result = preview_rename("old_val", "new_val", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        actions = [l["action"] for l in lines]
        assert "replace" in actions

    def test_preview_file_names_len_result_file_names_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_module.py").write_text("pass\n")
        result = preview_rename("old_module", "new_module", directory=str(tmp_path))

        assert len(result.file_names) == 1

    def test_preview_file_names_old_module_in_result_file_names_0_old_pa(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_module.py").write_text("pass\n")
        result = preview_rename("old_module", "new_module", directory=str(tmp_path))

        assert "old_module" in result.file_names[0]["old_path"]

    def test_preview_file_names_tmp_path_old_module_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_module.py").write_text("pass\n")
        result = preview_rename("old_module", "new_module", directory=str(tmp_path))

        assert (tmp_path / "old_module.py").exists()

    def test_preview_directory_names_len_result_dir_names_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "__init__.py").write_text("")
        result = preview_rename("old_pkg", "new_pkg", directory=str(tmp_path))

        assert len(result.dir_names) == 1

    def test_preview_directory_names_tmp_path_old_pkg_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "__init__.py").write_text("")
        result = preview_rename("old_pkg", "new_pkg", directory=str(tmp_path))

        assert (tmp_path / "old_pkg").exists()

    def test_preview_no_changes_for_no_matches_len_result_contents_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing here\n")
        result = preview_rename("nonexistent", "replacement", directory=str(tmp_path))

        assert len(result.contents) == 0

    def test_preview_no_changes_for_no_matches_len_result_file_names_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing here\n")
        result = preview_rename("nonexistent", "replacement", directory=str(tmp_path))

        assert len(result.file_names) == 0

    def test_preview_no_changes_for_no_matches_len_result_dir_names_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing here\n")
        result = preview_rename("nonexistent", "replacement", directory=str(tmp_path))

        assert len(result.dir_names) == 0

    def test_preview_multiple_files(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "a.py").write_text("old = 1\n")
        (tmp_path / "b.py").write_text("old = 2\n")
        (tmp_path / "c.py").write_text("no match\n")
        result = preview_rename("old", "new", directory=str(tmp_path))

        assert len(result.contents) == 2

    def test_preview_preserves_non_matching_lines_len_lines_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("line1\nold\nline3\n")
        result = preview_rename("old", "new", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert len(lines) == 1

    def test_preview_preserves_non_matching_lines_lines_0_line_num_2(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("line1\nold\nline3\n")
        result = preview_rename("old", "new", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert lines[0]["line_num"] == 2


# ===========================================================================
# Execute rename (live)
# ===========================================================================


class TestExecuteRename:
    def test_execute_file_contents_result_dry_run_is_false(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\n")
        result = _safe_execute("old_name", "new_name", tmp_path)

        assert result.dry_run is False

    def test_execute_file_contents_new_name_in_tmp_path_test_py_read_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\n")
        result = _safe_execute("old_name", "new_name", tmp_path)

        assert "new_name" in (tmp_path / "test.py").read_text()

    def test_execute_file_names_not_tmp_path_old_mod_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        assert not (tmp_path / "old_mod.py").exists()

    def test_execute_file_names_tmp_path_new_mod_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        assert (tmp_path / "new_mod.py").exists()

    def test_execute_directory_names_not_tmp_path_old_dir_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file.py").write_text("pass\n")
        _safe_execute("old_dir", "new_dir", tmp_path)

        assert not (tmp_path / "old_dir").exists()

    def test_execute_directory_names_tmp_path_new_dir_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file.py").write_text("pass\n")
        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir").exists()

    def test_execute_directory_names_tmp_path_new_dir_file_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file.py").write_text("pass\n")
        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir" / "file.py").exists()

    def test_execute_blocks_on_uncommitted_result_error_is_not_none(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old\n")
        result = execute_rename(
            "old",
            "new",
            directory=str(tmp_path),
            uncommitted_check_fn=lambda _dir: True,
        )

        assert result.error is not None

    def test_execute_blocks_on_uncommitted_uncommitted_in_result_error(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old\n")
        result = execute_rename(
            "old",
            "new",
            directory=str(tmp_path),
            uncommitted_check_fn=lambda _dir: True,
        )

        assert "Uncommitted" in result.error

    def test_execute_blocks_on_uncommitted_old_in_tmp_path_test_py_read_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old\n")
        result = execute_rename(
            "old",
            "new",
            directory=str(tmp_path),
            uncommitted_check_fn=lambda _dir: True,
        )

        assert "old" in (tmp_path / "test.py").read_text()

    def test_execute_deepest_dir_first_tmp_path_new_a_new_b_file_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_a").mkdir()
        (tmp_path / "old_a" / "old_b").mkdir()
        (tmp_path / "old_a" / "old_b" / "file.py").write_text("pass\n")
        result = _safe_execute("old_", "new_", tmp_path)

        assert (tmp_path / "new_a" / "new_b" / "file.py").exists()

    def test_execute_deepest_dir_first_len_result_dir_names_2(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_a").mkdir()
        (tmp_path / "old_a" / "old_b").mkdir()
        (tmp_path / "old_a" / "old_b" / "file.py").write_text("pass\n")
        result = _safe_execute("old_", "new_", tmp_path)

        assert len(result.dir_names) == 2

    def test_execute_force_bypasses_uncommitted_check_result_error_is_none(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old = 1\n")
        result = execute_rename(
            "old",
            "new",
            directory=str(tmp_path),
            force=True,
            uncommitted_check_fn=lambda _dir: True,
            safety_check_fn=lambda _dir: None,
        )

        assert result.error is None

    def test_execute_force_bypasses_uncommitted_check_new_in_tmp_path_test_py_read_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old = 1\n")
        result = execute_rename(
            "old",
            "new",
            directory=str(tmp_path),
            force=True,
            uncommitted_check_fn=lambda _dir: True,
            safety_check_fn=lambda _dir: None,
        )

        assert "new" in (tmp_path / "test.py").read_text()

    def test_execute_multiple_occurrences_per_line_text_strip_new_new_new(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old old old\n")
        result = _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert text.strip() == "new new new"

    def test_execute_multiple_occurrences_per_line_result_contents_0_matches_3(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old old old\n")
        result = _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert result.contents[0]["matches"] == 3

    def test_execute_preserves_file_with_no_matches_tmp_path_keep_py_read_text_no_match_here(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "keep.py").write_text("no match here\n")
        (tmp_path / "change.py").write_text("old = 1\n")
        _safe_execute("old", "new", tmp_path)

        assert (tmp_path / "keep.py").read_text() == "no match here\n"

    def test_execute_preserves_file_with_no_matches_new_in_tmp_path_change_py_read_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "keep.py").write_text("no match here\n")
        (tmp_path / "change.py").write_text("old = 1\n")
        _safe_execute("old", "new", tmp_path)

        assert "new" in (tmp_path / "change.py").read_text()

    def test_execute_content_and_filename_both_renamed_not_tmp_path_old_mod_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("import old_mod\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        assert not (tmp_path / "old_mod.py").exists()

    def test_execute_content_and_filename_both_renamed_tmp_path_new_mod_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("import old_mod\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        assert (tmp_path / "new_mod.py").exists()

    def test_execute_content_and_filename_both_renamed_import_new_mod_in_tmp_path_new_mod_py_re(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("import old_mod\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        assert "import new_mod" in (tmp_path / "new_mod.py").read_text()


# ===========================================================================
# Django-safe mode
# ===========================================================================


class TestDjangoSafe:
    def test_protects_db_table_db_table_old_table_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "class Meta:\n    db_table = 'old_table'\nold_table_var = 1\n"
        (tmp_path / "models.py").write_text(content)
        _safe_execute("old_table", "new_table", tmp_path)

        text = (tmp_path / "models.py").read_text()
        assert "db_table = 'old_table'" in text

    def test_protects_db_table_new_table_var_1_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "class Meta:\n    db_table = 'old_table'\nold_table_var = 1\n"
        (tmp_path / "models.py").write_text(content)
        _safe_execute("old_table", "new_table", tmp_path)

        text = (tmp_path / "models.py").read_text()
        assert "new_table_var = 1" in text

    def test_no_django_safe(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "db_table = 'old_table'\n"
        (tmp_path / "models.py").write_text(content)
        _safe_execute("old_table", "new_table", tmp_path, django_safe=False)

        text = (tmp_path / "models.py").read_text()
        assert "new_table" in text

    def test_protects_related_name_related_name_old_items_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "    related_name='old_items'\nold_items = []\n"
        (tmp_path / "models.py").write_text(content)
        _safe_execute("old_items", "new_items", tmp_path)

        text = (tmp_path / "models.py").read_text()
        assert "related_name='old_items'" in text

    def test_protects_related_name_new_items_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "    related_name='old_items'\nold_items = []\n"
        (tmp_path / "models.py").write_text(content)
        _safe_execute("old_items", "new_items", tmp_path)

        text = (tmp_path / "models.py").read_text()
        assert "new_items = []" in text

    def test_protects_installed_apps_installed_apps_old_app_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "INSTALLED_APPS = ['old_app']\nold_app_var = 1\n"
        (tmp_path / "settings.py").write_text(content)
        _safe_execute("old_app", "new_app", tmp_path)

        text = (tmp_path / "settings.py").read_text()
        assert "INSTALLED_APPS = ['old_app']" in text

    def test_protects_installed_apps_new_app_var_1_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "INSTALLED_APPS = ['old_app']\nold_app_var = 1\n"
        (tmp_path / "settings.py").write_text(content)
        _safe_execute("old_app", "new_app", tmp_path)

        text = (tmp_path / "settings.py").read_text()
        assert "new_app_var = 1" in text

    def test_protects_old_name_new_name_in_migration_old_name_old_field_in_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        content = "old_name='old_field'\nnew_name='new_field'\nold_field = 1\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old_field", "new_field", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert "old_name='old_field'" in text

    def test_protects_old_name_new_name_in_migration_new_name_new_field_in_text(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        content = "old_name='old_field'\nnew_name='new_field'\nold_field = 1\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old_field", "new_field", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert "new_name='new_field'" in text


# ===========================================================================
# Symlinks
# ===========================================================================


class TestSymlinks:
    def test_symlink_target_update_len_result_symlink_targets_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_target.py"
        target.write_text("pass\n")
        link = tmp_path / "link.py"
        link.symlink_to("old_target.py")

        config = RenameConfig(
            pattern="old_target",
            replacement="new_target",
            directory=str(tmp_path),
            dry_run=False,
        )
        result = bulk_rename(config, safety_check_fn=lambda _dir: None)

        assert len(result.symlink_targets) == 1

    def test_symlink_target_update_os_readlink_str_link_new_target_py(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_target.py"
        target.write_text("pass\n")
        link = tmp_path / "link.py"
        link.symlink_to("old_target.py")

        config = RenameConfig(
            pattern="old_target",
            replacement="new_target",
            directory=str(tmp_path),
            dry_run=False,
        )
        result = bulk_rename(config, safety_check_fn=lambda _dir: None)

        assert os.readlink(str(link)) == "new_target.py"

    def test_symlink_name_rename_len_result_symlink_names_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "target.py"
        target.write_text("pass\n")
        link = tmp_path / "old_link.py"
        link.symlink_to("target.py")

        config = RenameConfig(
            pattern="old_link",
            replacement="new_link",
            directory=str(tmp_path),
            dry_run=False,
        )
        result = bulk_rename(config, safety_check_fn=lambda _dir: None)

        assert len(result.symlink_names) == 1

    def test_symlink_name_rename_tmp_path_new_link_py_is_symlink(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "target.py"
        target.write_text("pass\n")
        link = tmp_path / "old_link.py"
        link.symlink_to("target.py")

        config = RenameConfig(
            pattern="old_link",
            replacement="new_link",
            directory=str(tmp_path),
            dry_run=False,
        )
        result = bulk_rename(config, safety_check_fn=lambda _dir: None)

        assert (tmp_path / "new_link.py").is_symlink()

    def test_symlink_target_and_name_both_updated_len_result_symlink_targets_1(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_file.py"
        target.write_text("pass\n")
        link = tmp_path / "old_link.py"
        link.symlink_to("old_file.py")

        config = RenameConfig(
            pattern="old_",
            replacement="new_",
            directory=str(tmp_path),
            dry_run=False,
        )
        result = bulk_rename(config, safety_check_fn=lambda _dir: None)

        assert len(result.symlink_targets) == 1

    def test_symlink_target_and_name_both_updated_len_result_symlink_names_1(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_file.py"
        target.write_text("pass\n")
        link = tmp_path / "old_link.py"
        link.symlink_to("old_file.py")

        config = RenameConfig(
            pattern="old_",
            replacement="new_",
            directory=str(tmp_path),
            dry_run=False,
        )
        result = bulk_rename(config, safety_check_fn=lambda _dir: None)

        assert len(result.symlink_names) == 1

    def test_symlink_collision_detected(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "target.py"
        target.write_text("pass\n")
        (tmp_path / "new_link.py").write_text("existing\n")
        link = tmp_path / "old_link.py"
        link.symlink_to("target.py")

        result = preview_rename("old_link", "new_link", directory=str(tmp_path))

        collisions = [c for c in result.collisions if c["type"] == "symlink"]
        assert len(collisions) == 1


# ===========================================================================
# Collision detection
# ===========================================================================


class TestCollisions:
    def test_file_collision_detected_in_dry_run_len_result_collisions_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = preview_rename("old_mod", "new_mod", directory=str(tmp_path))

        assert len(result.collisions) == 1

    def test_file_collision_detected_in_dry_run_result_collisions_0_type_file(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = preview_rename("old_mod", "new_mod", directory=str(tmp_path))

        assert result.collisions[0]["type"] == "file"

    def test_file_collision_detected_in_dry_run_new_mod_py_in_result_collisions_0_path(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = preview_rename("old_mod", "new_mod", directory=str(tmp_path))

        assert "new_mod.py" in result.collisions[0]["path"]

    def test_dir_collision_detected_in_dry_run_len_result_collisions_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "__init__.py").write_text("")
        (tmp_path / "new_pkg").mkdir()
        (tmp_path / "new_pkg" / "__init__.py").write_text("")

        result = preview_rename("old_pkg", "new_pkg", directory=str(tmp_path))

        assert len(result.collisions) >= 1
        types = [c["type"] for c in result.collisions]

    def test_dir_collision_detected_in_dry_run_directory_in_types(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "__init__.py").write_text("")
        (tmp_path / "new_pkg").mkdir()
        (tmp_path / "new_pkg" / "__init__.py").write_text("")

        result = preview_rename("old_pkg", "new_pkg", directory=str(tmp_path))

        types = [c["type"] for c in result.collisions]
        assert "directory" in types

    def test_no_collision_when_target_absent(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")

        result = preview_rename("old_mod", "new_mod", directory=str(tmp_path))

        assert len(result.collisions) == 0

    def test_execute_blocks_on_file_collision_result_error_is_not_none(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = _safe_execute("old_mod", "new_mod", tmp_path)

        assert result.error is not None

    def test_execute_blocks_on_file_collision_collision_in_result_error(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = _safe_execute("old_mod", "new_mod", tmp_path)

        assert "Collision" in result.error

    def test_execute_blocks_on_file_collision_tmp_path_old_mod_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = _safe_execute("old_mod", "new_mod", tmp_path)

        assert (tmp_path / "old_mod.py").exists()

    def test_execute_blocks_on_file_collision_existing_in_tmp_path_new_mod_py_read_tex(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        (tmp_path / "new_mod.py").write_text("existing\n")

        result = _safe_execute("old_mod", "new_mod", tmp_path)

        assert "existing" in (tmp_path / "new_mod.py").read_text()

    def test_collision_summary_count(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_a.py").write_text("pass\n")
        (tmp_path / "new_a.py").write_text("existing\n")
        (tmp_path / "old_b.py").write_text("pass\n")
        (tmp_path / "new_b.py").write_text("existing\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert result.summary["collisions"] == 2

    def test_dir_collision_allows_merge_result_error_is_none(self, tmp_path):
        """Directory collisions don't block execution (merge instead)."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "a.py").write_text("pass\n")
        (tmp_path / "new_pkg").mkdir()
        (tmp_path / "new_pkg" / "b.py").write_text("pass\n")

        result = _safe_execute("old_pkg", "new_pkg", tmp_path)

        # Should succeed (dir collisions merged, not blocked)
        assert result.error is None

    def test_dir_collision_allows_merge_tmp_path_new_pkg_a_py_exists(self, tmp_path):
        """Directory collisions don't block execution (merge instead)."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "a.py").write_text("pass\n")
        (tmp_path / "new_pkg").mkdir()
        (tmp_path / "new_pkg" / "b.py").write_text("pass\n")

        result = _safe_execute("old_pkg", "new_pkg", tmp_path)

        # Should succeed (dir collisions merged, not blocked)
        assert (tmp_path / "new_pkg" / "a.py").exists()

    def test_dir_collision_allows_merge_tmp_path_new_pkg_b_py_exists(self, tmp_path):
        """Directory collisions don't block execution (merge instead)."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "a.py").write_text("pass\n")
        (tmp_path / "new_pkg").mkdir()
        (tmp_path / "new_pkg" / "b.py").write_text("pass\n")

        result = _safe_execute("old_pkg", "new_pkg", tmp_path)

        # Should succeed (dir collisions merged, not blocked)
        assert (tmp_path / "new_pkg" / "b.py").exists()


# ===========================================================================
# Directory merge
# ===========================================================================


class TestDirectoryMerge:
    def test_merge_moves_all_children_not_tmp_path_old_dir_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file1.py").write_text("one\n")
        (tmp_path / "old_dir" / "file2.py").write_text("two\n")
        (tmp_path / "new_dir").mkdir()
        (tmp_path / "new_dir" / "file3.py").write_text("three\n")

        _safe_execute("old_dir", "new_dir", tmp_path)

        assert not (tmp_path / "old_dir").exists()

    def test_merge_moves_all_children_tmp_path_new_dir_file1_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file1.py").write_text("one\n")
        (tmp_path / "old_dir" / "file2.py").write_text("two\n")
        (tmp_path / "new_dir").mkdir()
        (tmp_path / "new_dir" / "file3.py").write_text("three\n")

        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir" / "file1.py").exists()

    def test_merge_moves_all_children_tmp_path_new_dir_file2_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file1.py").write_text("one\n")
        (tmp_path / "old_dir" / "file2.py").write_text("two\n")
        (tmp_path / "new_dir").mkdir()
        (tmp_path / "new_dir" / "file3.py").write_text("three\n")

        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir" / "file2.py").exists()

    def test_merge_moves_all_children_tmp_path_new_dir_file3_py_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file1.py").write_text("one\n")
        (tmp_path / "old_dir" / "file2.py").write_text("two\n")
        (tmp_path / "new_dir").mkdir()
        (tmp_path / "new_dir" / "file3.py").write_text("three\n")

        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir" / "file3.py").exists()

    def test_merge_nested_directories_tmp_path_new_dir_sub_nested_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "sub").mkdir()
        (tmp_path / "old_dir" / "sub" / "nested.py").write_text("nested\n")
        (tmp_path / "new_dir").mkdir()
        (tmp_path / "new_dir" / "sub").mkdir()
        (tmp_path / "new_dir" / "sub" / "existing.py").write_text("existing\n")

        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir" / "sub" / "nested.py").exists()

    def test_merge_nested_directories_tmp_path_new_dir_sub_existing_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "sub").mkdir()
        (tmp_path / "old_dir" / "sub" / "nested.py").write_text("nested\n")
        (tmp_path / "new_dir").mkdir()
        (tmp_path / "new_dir" / "sub").mkdir()
        (tmp_path / "new_dir" / "sub" / "existing.py").write_text("existing\n")

        _safe_execute("old_dir", "new_dir", tmp_path)

        assert (tmp_path / "new_dir" / "sub" / "existing.py").exists()


# ===========================================================================
# Summary
# ===========================================================================


class TestSummary:
    def test_summary_counts_files_lines_and_renames_result_summary_content_files_1(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_file.py").write_text("old_name = 1\nold_name = 2\n")
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "test.txt").write_text("pass\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert result.summary["content_files"] >= 1

    def test_summary_counts_files_lines_and_renames_result_summary_content_matches_2(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_file.py").write_text("old_name = 1\nold_name = 2\n")
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "test.txt").write_text("pass\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert result.summary["content_matches"] >= 2

    def test_summary_counts_files_lines_and_renames_result_summary_files_renamed_1(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_file.py").write_text("old_name = 1\nold_name = 2\n")
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "test.txt").write_text("pass\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert result.summary["files_renamed"] >= 1

    def test_summary_counts_files_lines_and_renames_result_summary_dirs_renamed_1(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_file.py").write_text("old_name = 1\nold_name = 2\n")
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "test.txt").write_text("pass\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert result.summary["dirs_renamed"] >= 1

    def test_summary_protected_files_count(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "models.py").write_text("db_table = 'old_val'\nold_val = 1\n")
        (tmp_path / "clean.py").write_text("old_val = 2\n")

        result = preview_rename("old_val", "new_val", directory=str(tmp_path))

        assert result.summary["protected_files"] == 1

    def test_summary_zero_when_no_matches_result_summary_content_files_0(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing\n")
        result = preview_rename("nonexistent", "replacement", directory=str(tmp_path))

        assert result.summary["content_files"] == 0

    def test_summary_zero_when_no_matches_result_summary_files_renamed_0(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing\n")
        result = preview_rename("nonexistent", "replacement", directory=str(tmp_path))

        assert result.summary["files_renamed"] == 0

    def test_summary_zero_when_no_matches_result_summary_dirs_renamed_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing\n")
        result = preview_rename("nonexistent", "replacement", directory=str(tmp_path))

        assert result.summary["dirs_renamed"] == 0


# ===========================================================================
# Skip IDs
# ===========================================================================


class TestSkipIds:
    def test_skip_file_level_old_in_tmp_path_a_py_read_text(self, tmp_path):
        """Skip all changes in a specific file by file-level ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "a.py").write_text("old = 1\n")
        (tmp_path / "b.py").write_text("old = 2\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        a_id = [c["id"] for c in preview.contents if "a.py" in c["file"]][0]
        _safe_execute("old", "new", tmp_path, skip_ids=[a_id])
        assert "old" in (tmp_path / "a.py").read_text()

    def test_skip_file_level_new_in_tmp_path_b_py_read_text(self, tmp_path):
        """Skip all changes in a specific file by file-level ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "a.py").write_text("old = 1\n")
        (tmp_path / "b.py").write_text("old = 2\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        a_id = [c["id"] for c in preview.contents if "a.py" in c["file"]][0]
        _safe_execute("old", "new", tmp_path, skip_ids=[a_id])
        assert "new" in (tmp_path / "b.py").read_text()

    def test_skip_line_level_old_a_in_text(self, tmp_path):
        """Skip a specific line by line-level ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_a = 1\nkeep = 2\nold_b = 3\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        file_result = preview.contents[0]
        line_id = [l["id"] for l in file_result["lines"] if l["line_num"] == 1][0]
        _safe_execute("old", "new", tmp_path, skip_ids=[line_id])
        text = (tmp_path / "test.py").read_text()
        assert "old_a" in text

    def test_skip_line_level_new_b_in_text(self, tmp_path):
        """Skip a specific line by line-level ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_a = 1\nkeep = 2\nold_b = 3\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        file_result = preview.contents[0]
        line_id = [l["id"] for l in file_result["lines"] if l["line_num"] == 1][0]
        _safe_execute("old", "new", tmp_path, skip_ids=[line_id])
        text = (tmp_path / "test.py").read_text()
        assert "new_b" in text

    def test_skip_dir_rename(self, tmp_path):
        """Skip a directory rename by ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file.py").write_text("pass\n")
        preview = preview_rename("old_dir", "new_dir", directory=str(tmp_path))
        dir_id = preview.dir_names[0]["id"]
        _safe_execute("old_dir", "new_dir", tmp_path, skip_ids=[dir_id])
        assert (tmp_path / "old_dir").exists()

    def test_skip_file_rename_tmp_path_old_mod_py_exists(self, tmp_path):
        """Skip a file rename by ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        preview = preview_rename("old_mod", "new_mod", directory=str(tmp_path))
        file_id = preview.file_names[0]["id"]
        _safe_execute("old_mod", "new_mod", tmp_path, skip_ids=[file_id])
        assert (tmp_path / "old_mod.py").exists()

    def test_skip_file_rename_not_tmp_path_new_mod_py_exists(self, tmp_path):
        """Skip a file rename by ID."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("pass\n")
        preview = preview_rename("old_mod", "new_mod", directory=str(tmp_path))
        file_id = preview.file_names[0]["id"]
        _safe_execute("old_mod", "new_mod", tmp_path, skip_ids=[file_id])
        assert not (tmp_path / "new_mod.py").exists()

    def test_skip_symlink_target(self, tmp_path):
        """Skip a symlink target update by ID."""
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_target.py"
        target.write_text("pass\n")
        link = tmp_path / "link.py"
        link.symlink_to("old_target.py")

        preview = preview_rename("old_target", "new_target", directory=str(tmp_path))
        st_id = preview.symlink_targets[0]["id"]

        execute_rename(
            "old_target",
            "new_target",
            directory=str(tmp_path),
            skip_ids=[st_id],
            uncommitted_check_fn=lambda _dir: False,
            safety_check_fn=lambda _dir: None,
        )

        assert os.readlink(str(link)) == "old_target.py"

    def test_ids_in_preview_id_in_result_contents_0(self, tmp_path):
        """Preview output includes IDs."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old = 1\n")
        result = preview_rename("old", "new", directory=str(tmp_path))
        assert "id" in result.contents[0]

    def test_ids_in_preview_result_contents_0_id_startswith_c(self, tmp_path):
        """Preview output includes IDs."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old = 1\n")
        result = preview_rename("old", "new", directory=str(tmp_path))
        assert result.contents[0]["id"].startswith("c-")

    def test_ids_in_preview_id_in_result_contents_0_lines_0(self, tmp_path):
        """Preview output includes IDs."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old = 1\n")
        result = preview_rename("old", "new", directory=str(tmp_path))
        assert "id" in result.contents[0]["lines"][0]

    def test_ids_in_preview_l_in_result_contents_0_lines_0_id(self, tmp_path):
        """Preview output includes IDs."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old = 1\n")
        result = preview_rename("old", "new", directory=str(tmp_path))
        assert "-L" in result.contents[0]["lines"][0]["id"]

    def test_skip_multiple_ids_old_in_tmp_path_a_py_read_text(self, tmp_path):
        """Skip multiple items at once."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "a.py").write_text("old = 1\n")
        (tmp_path / "b.py").write_text("old = 2\n")
        (tmp_path / "c.py").write_text("old = 3\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        ids_to_skip = [
            c["id"]
            for c in preview.contents
            if "a.py" in c["file"] or "b.py" in c["file"]
        ]
        _safe_execute("old", "new", tmp_path, skip_ids=ids_to_skip)
        assert "old" in (tmp_path / "a.py").read_text()

    def test_skip_multiple_ids_old_in_tmp_path_b_py_read_text(self, tmp_path):
        """Skip multiple items at once."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "a.py").write_text("old = 1\n")
        (tmp_path / "b.py").write_text("old = 2\n")
        (tmp_path / "c.py").write_text("old = 3\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        ids_to_skip = [
            c["id"]
            for c in preview.contents
            if "a.py" in c["file"] or "b.py" in c["file"]
        ]
        _safe_execute("old", "new", tmp_path, skip_ids=ids_to_skip)
        assert "old" in (tmp_path / "b.py").read_text()

    def test_skip_multiple_ids_new_in_tmp_path_c_py_read_text(self, tmp_path):
        """Skip multiple items at once."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "a.py").write_text("old = 1\n")
        (tmp_path / "b.py").write_text("old = 2\n")
        (tmp_path / "c.py").write_text("old = 3\n")
        preview = preview_rename("old", "new", directory=str(tmp_path))
        ids_to_skip = [
            c["id"]
            for c in preview.contents
            if "a.py" in c["file"] or "b.py" in c["file"]
        ]
        _safe_execute("old", "new", tmp_path, skip_ids=ids_to_skip)
        assert "new" in (tmp_path / "c.py").read_text()


# ===========================================================================
# Django app rename warnings
# ===========================================================================


class TestDjangoAppWarning:
    def test_warning_emitted_for_app_dir_rename_warnings_in_result_summary(
        self, tmp_path
    ):
        """Renaming a directory containing apps.py triggers warning."""
        # Arrange
        # Act
        # Assert
        app_dir = tmp_path / "old_app"
        app_dir.mkdir()
        (app_dir / "apps.py").write_text("class Config: pass\n")
        (app_dir / "__init__.py").write_text("")

        result = _safe_execute("old_app", "new_app", tmp_path)

        assert "warnings" in result.summary

    def test_warning_emitted_for_app_dir_rename_any_django_app_rename_in_w_for_w_in_resu(
        self, tmp_path
    ):
        """Renaming a directory containing apps.py triggers warning."""
        # Arrange
        # Act
        # Assert
        app_dir = tmp_path / "old_app"
        app_dir.mkdir()
        (app_dir / "apps.py").write_text("class Config: pass\n")
        (app_dir / "__init__.py").write_text("")

        result = _safe_execute("old_app", "new_app", tmp_path)

        assert any("DJANGO APP RENAME" in w for w in result.summary["warnings"])

    def test_no_warning_for_regular_dir(self, tmp_path):
        """Regular directory rename does not trigger warning."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_dir").mkdir()
        (tmp_path / "old_dir" / "file.py").write_text("pass\n")

        result = _safe_execute("old_dir", "new_dir", tmp_path)

        assert "warnings" not in result.summary

    def test_warning_in_preview_warnings_in_result_summary(self, tmp_path):
        """Warning also shown in dry run preview."""
        # Arrange
        # Act
        # Assert
        app_dir = tmp_path / "old_app"
        app_dir.mkdir()
        (app_dir / "apps.py").write_text("class Config: pass\n")
        (app_dir / "__init__.py").write_text("")

        result = preview_rename("old_app", "new_app", directory=str(tmp_path))

        assert "warnings" in result.summary

    def test_warning_in_preview_any_django_app_rename_in_w_for_w_in_resu(
        self, tmp_path
    ):
        """Warning also shown in dry run preview."""
        # Arrange
        # Act
        # Assert
        app_dir = tmp_path / "old_app"
        app_dir.mkdir()
        (app_dir / "apps.py").write_text("class Config: pass\n")
        (app_dir / "__init__.py").write_text("")

        result = preview_rename("old_app", "new_app", directory=str(tmp_path))

        assert any("DJANGO APP RENAME" in w for w in result.summary["warnings"])

    def test_warning_includes_old_and_new_names_modulemaker_app_in_warning(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        app_dir = tmp_path / "modulemaker_app"
        app_dir.mkdir()
        (app_dir / "apps.py").write_text("class Config: pass\n")
        (app_dir / "__init__.py").write_text("")

        result = preview_rename(
            "modulemaker_app", "appmaker_app", directory=str(tmp_path)
        )

        warning = result.summary["warnings"][0]
        assert "modulemaker_app" in warning

    def test_warning_includes_old_and_new_names_appmaker_app_in_warning(self, tmp_path):
        # Arrange
        # Act
        # Assert
        app_dir = tmp_path / "modulemaker_app"
        app_dir.mkdir()
        (app_dir / "apps.py").write_text("class Config: pass\n")
        (app_dir / "__init__.py").write_text("")

        result = preview_rename(
            "modulemaker_app", "appmaker_app", directory=str(tmp_path)
        )

        warning = result.summary["warnings"][0]
        assert "appmaker_app" in warning


# ===========================================================================
# Safety checks (_safety.py)
# ===========================================================================


class TestSafety:
    def test_has_uncommitted_changes_not_git(self, tmp_path):
        # Arrange
        # Act
        # Assert
        assert has_uncommitted_changes(str(tmp_path)) is False

    def test_is_git_repo_false_for_tmp(self, tmp_path):
        # Arrange
        # Act
        # Assert
        assert is_git_repo(str(tmp_path)) is False

    def test_is_git_repo_true_for_real_repo(self):
        """Current project should be a git repo."""
        # Arrange
        # Act
        # Assert
        project_root = Path(__file__).resolve().parents[1]
        assert is_git_repo(str(project_root)) is True

    def test_check_directory_safety_blocks_root_result_is_not_none(self):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety("/")
        assert result is not None

    def test_check_directory_safety_blocks_root_system_directory_in_result(self):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety("/")
        assert "system directory" in result

    def test_check_directory_safety_blocks_home(self):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety("/home")
        assert result is not None

    def test_check_directory_safety_blocks_usr(self):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety("/usr")
        assert result is not None

    def test_check_directory_safety_blocks_shallow_path_result_is_not_none(self):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety("/ab")
        assert result is not None

    def test_check_directory_safety_blocks_shallow_path_shallow_in_result(self):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety("/ab")
        assert "shallow" in result

    def test_check_directory_safety_requires_git_result_is_not_none(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety(str(tmp_path))
        assert result is not None

    def test_check_directory_safety_requires_git_git_in_result_lower(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = check_directory_safety(str(tmp_path))
        assert "git" in result.lower()

    def test_create_backup_writes_zip_with_files_backup_dir_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "file.py").write_text("content\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("nested\n")

        backup_dir = create_backup(str(tmp_path), "old", "new")

        assert backup_dir.exists()
        meta = (backup_dir / "operation.txt").read_text()

    def test_create_backup_writes_zip_with_files_backup_dir_operation_txt_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "file.py").write_text("content\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("nested\n")

        backup_dir = create_backup(str(tmp_path), "old", "new")

        assert (backup_dir / "operation.txt").exists()
        meta = (backup_dir / "operation.txt").read_text()

    def test_create_backup_writes_zip_with_files_pattern_old_in_meta(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "file.py").write_text("content\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("nested\n")

        backup_dir = create_backup(str(tmp_path), "old", "new")

        meta = (backup_dir / "operation.txt").read_text()
        assert "pattern=old" in meta

    def test_create_backup_writes_zip_with_files_replacement_new_in_meta(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "file.py").write_text("content\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("nested\n")

        backup_dir = create_backup(str(tmp_path), "old", "new")

        meta = (backup_dir / "operation.txt").read_text()
        assert "replacement=new" in meta

    def test_create_backup_writes_zip_with_files_backup_dir_original_file_py_exists(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "file.py").write_text("content\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("nested\n")

        backup_dir = create_backup(str(tmp_path), "old", "new")

        meta = (backup_dir / "operation.txt").read_text()
        assert (backup_dir / "original" / "file.py").exists()

    def test_create_backup_writes_zip_with_files_backup_dir_original_subdir_nested_py_exi(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        (tmp_path / "file.py").write_text("content\n")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.py").write_text("nested\n")

        backup_dir = create_backup(str(tmp_path), "old", "new")

        meta = (backup_dir / "operation.txt").read_text()
        assert (backup_dir / "original" / "subdir" / "nested.py").exists()


# ===========================================================================
# I/O helpers (_io.py)
# ===========================================================================


class TestIO:
    def test_write_text_normal(self, tmp_path):
        # Arrange
        # Act
        # Assert
        f = tmp_path / "test.txt"
        write_text(f, "hello world")
        assert f.read_text() == "hello world"

    def test_rename_path_normal_not_src_exists(self, tmp_path):
        # Arrange
        # Act
        # Assert
        src = tmp_path / "old.txt"
        dst = tmp_path / "new.txt"
        src.write_text("content")
        rename_path(src, dst)
        assert not src.exists()

    def test_rename_path_normal_dst_read_text_content(self, tmp_path):
        # Arrange
        # Act
        # Assert
        src = tmp_path / "old.txt"
        dst = tmp_path / "new.txt"
        src.write_text("content")
        rename_path(src, dst)
        assert dst.read_text() == "content"

    def test_unlink_path_normal(self, tmp_path):
        # Arrange
        # Act
        # Assert
        f = tmp_path / "delete_me.txt"
        f.write_text("bye")
        unlink_path(f)
        assert not f.exists()

    def test_mkdir_creates_directory_at_target(self, tmp_path):
        # Arrange
        # Act
        # Assert
        d = tmp_path / "new_dir"
        mkdir(d)
        assert d.is_dir()

    def test_mkdir_with_parents_creates_intermediate_dirs(self, tmp_path):
        # Arrange
        # Act
        # Assert
        d = tmp_path / "a" / "b" / "c"
        mkdir(d, parents=True)
        assert d.is_dir()

    def test_rmdir_removes_empty_directory(self, tmp_path):
        # Arrange
        # Act
        # Assert
        d = tmp_path / "empty_dir"
        d.mkdir()
        rmdir(d)
        assert not d.exists()

    def test_symlink_to_normal_link_is_symlink(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "target.txt"
        target.write_text("content")
        link = tmp_path / "link.txt"
        symlink_to(link, "target.txt")
        assert link.is_symlink()

    def test_symlink_to_normal_os_readlink_str_link_target_txt(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "target.txt"
        target.write_text("content")
        link = tmp_path / "link.txt"
        symlink_to(link, "target.txt")
        assert os.readlink(str(link)) == "target.txt"

    def test_set_sudo_password_and_clear_rename_io__sudo_password_secret123(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev.rename import io as rename_io

        set_sudo_password("secret123")
        assert rename_io._sudo_password == "secret123"
        set_sudo_password(None)

    def test_set_sudo_password_and_clear_rename_io__sudo_password_is_none(self):
        # Arrange
        # Act
        # Assert
        from scitex_dev.rename import io as rename_io

        set_sudo_password("secret123")
        set_sudo_password(None)
        assert rename_io._sudo_password is None

    def test_write_text_sudo_calls_subprocess_len_calls_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        f = tmp_path / "test.txt"
        calls: list[tuple] = []

        def _runner(argv, input_data=None):
            calls.append((argv, input_data))

        write_text(f, "hello", use_sudo=True, runner=_runner)
        assert len(calls) == 1

    def test_write_text_sudo_calls_subprocess_calls_0_0_tee_str_f(self, tmp_path):
        # Arrange
        # Act
        # Assert
        f = tmp_path / "test.txt"
        calls: list[tuple] = []

        def _runner(argv, input_data=None):
            calls.append((argv, input_data))

        write_text(f, "hello", use_sudo=True, runner=_runner)
        assert calls[0][0] == ["tee", str(f)]

    def test_rename_path_sudo_calls_subprocess(self, tmp_path):
        # Arrange
        # Act
        # Assert
        src = tmp_path / "old.txt"
        dst = tmp_path / "new.txt"
        calls: list[list[str]] = []
        rename_path(src, dst, use_sudo=True, runner=lambda argv: calls.append(argv))
        assert calls == [["mv", str(src), str(dst)]]

    def test_mkdir_sudo_with_parents(self, tmp_path):
        # Arrange
        # Act
        # Assert
        d = tmp_path / "new_dir"
        calls: list[list[str]] = []
        mkdir(d, parents=True, use_sudo=True, runner=lambda argv: calls.append(argv))
        assert calls == [["mkdir", "-p", str(d)]]


# ===========================================================================
# Find matching files
# ===========================================================================


class TestFindMatchingFiles:
    def test_search_respects_exclude_patterns_good_py_in_file_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "good.py").write_text("pattern\n")
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "bad.py").write_text("pattern\n")

        config = RenameConfig(pattern="pattern", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        file_names = [f.name for f in files]
        assert "good.py" in file_names

    def test_search_respects_exclude_patterns_bad_py_not_in_file_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "good.py").write_text("pattern\n")
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "bad.py").write_text("pattern\n")

        config = RenameConfig(pattern="pattern", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        file_names = [f.name for f in files]
        assert "bad.py" not in file_names

    def test_respects_extension_filter_code_py_in_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "code.py").write_text("match\n")
        (tmp_path / "image.jpg").write_text("match\n")

        config = RenameConfig(pattern="match", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        names = [f.name for f in files]
        assert "code.py" in names

    def test_respects_extension_filter_image_jpg_not_in_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "code.py").write_text("match\n")
        (tmp_path / "image.jpg").write_text("match\n")

        config = RenameConfig(pattern="match", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        names = [f.name for f in files]
        assert "image.jpg" not in names

    def test_search_skips_symlinked_paths_real_py_in_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "real.py").write_text("match\n")
        (tmp_path / "link.py").symlink_to("real.py")

        config = RenameConfig(pattern="match", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        names = [f.name for f in files]
        assert "real.py" in names

    def test_search_skips_symlinked_paths_link_py_not_in_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "real.py").write_text("match\n")
        (tmp_path / "link.py").symlink_to("real.py")

        config = RenameConfig(pattern="match", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        names = [f.name for f in files]
        assert "link.py" not in names

    def test_content_match_filter_len_with_content_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "has_match.py").write_text("target_pattern\n")
        (tmp_path / "no_match.py").write_text("nothing here\n")

        config = RenameConfig(pattern="target_pattern", replacement="new")
        with_content = find_matching_files(
            str(tmp_path), config, need_content_match=True
        )
        without_content = find_matching_files(
            str(tmp_path), config, need_content_match=False
        )

        assert len(with_content) == 1

    def test_content_match_filter_len_without_content_2(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "has_match.py").write_text("target_pattern\n")
        (tmp_path / "no_match.py").write_text("nothing here\n")

        config = RenameConfig(pattern="target_pattern", replacement="new")
        with_content = find_matching_files(
            str(tmp_path), config, need_content_match=True
        )
        without_content = find_matching_files(
            str(tmp_path), config, need_content_match=False
        )

        assert len(without_content) == 2

    def test_recursive_search_walks_nested_dirs(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b").mkdir()
        (tmp_path / "a" / "b" / "deep.py").write_text("match\n")

        config = RenameConfig(pattern="match", replacement="new")
        files = find_matching_files(str(tmp_path), config, need_content_match=True)

        assert any("deep.py" in f.name for f in files)


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_empty_file_yields_no_changes(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "empty.py").write_text("")
        result = preview_rename("anything", "something", directory=str(tmp_path))
        assert len(result.contents) == 0

    def test_pattern_in_directory_and_file_len_result_dir_names_1(self, tmp_path):
        """Pattern matches both directory name and file inside it."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "old_mod.py").write_text("old_ref\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert len(result.dir_names) >= 1

    def test_pattern_in_directory_and_file_len_result_file_names_1(self, tmp_path):
        """Pattern matches both directory name and file inside it."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "old_mod.py").write_text("old_ref\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert len(result.file_names) >= 1

    def test_pattern_in_directory_and_file_len_result_contents_1(self, tmp_path):
        """Pattern matches both directory name and file inside it."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_pkg").mkdir()
        (tmp_path / "old_pkg" / "old_mod.py").write_text("old_ref\n")

        result = preview_rename("old_", "new_", directory=str(tmp_path))

        assert len(result.contents) >= 1

    def test_pattern_is_substring(self, tmp_path):
        """Pattern matches as substring within larger tokens."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_longer_name\nold\nsome_old_thing\n")
        result = preview_rename("old", "new", directory=str(tmp_path))

        lines = result.contents[0]["lines"]
        assert len(lines) == 3  # All three lines contain "old"

    def test_replacement_contains_pattern(self, tmp_path):
        """Replacement that contains the original pattern should work."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("app\n")
        _safe_execute("app", "appmaker", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert text.strip() == "appmaker"

    def test_unicode_content_preserved_through_rename_new_name_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("# Comment: old_name → new\nold_name = 1\n")
        result = _safe_execute("old_name", "new_name", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert "new_name" in text

    def test_unicode_content_preserved_through_rename_in_text(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("# Comment: old_name → new\nold_name = 1\n")
        result = _safe_execute("old_name", "new_name", tmp_path)

        text = (tmp_path / "test.py").read_text()
        assert "→" in text

    def test_multiline_file_preserved_lines_0_line1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "line1\nold = 1\nline3\nold = 2\nline5\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        lines = text.split("\n")
        assert lines[0] == "line1"

    def test_multiline_file_preserved_new_in_lines_1(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "line1\nold = 1\nline3\nold = 2\nline5\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        lines = text.split("\n")
        assert "new" in lines[1]

    def test_multiline_file_preserved_lines_2_line3(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "line1\nold = 1\nline3\nold = 2\nline5\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        lines = text.split("\n")
        assert lines[2] == "line3"

    def test_multiline_file_preserved_new_in_lines_3(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "line1\nold = 1\nline3\nold = 2\nline5\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        lines = text.split("\n")
        assert "new" in lines[3]

    def test_multiline_file_preserved_lines_4_line5(self, tmp_path):
        # Arrange
        # Act
        # Assert
        content = "line1\nold = 1\nline3\nold = 2\nline5\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute("old", "new", tmp_path)

        text = (tmp_path / "test.py").read_text()
        lines = text.split("\n")
        assert lines[4] == "line5"

    def test_no_partial_extension_match_tmp_path_new_name_py_exists(self, tmp_path):
        """File renames should not create double extensions."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_name.py").write_text("pass\n")
        _safe_execute("old_name", "new_name", tmp_path)

        assert (tmp_path / "new_name.py").exists()

    def test_no_partial_extension_match_not_tmp_path_new_name_py_py_exists(
        self, tmp_path
    ):
        """File renames should not create double extensions."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_name.py").write_text("pass\n")
        _safe_execute("old_name", "new_name", tmp_path)

        assert not (tmp_path / "new_name.py.py").exists()

    def test_preserves_file_permissions(self, tmp_path):
        # Arrange
        # Act
        # Assert
        f = tmp_path / "test.py"
        f.write_text("old = 1\n")
        f.chmod(0o755)
        _safe_execute("old", "new", tmp_path)

        # File should still have content updated
        assert "new" in f.read_text()


# ===========================================================================
# Execution order
# ===========================================================================


class TestExecutionOrder:
    def test_contents_before_file_rename_tmp_path_new_mod_py_exists(self, tmp_path):
        """Content replacement happens before file rename."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("import old_mod\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        # File should be renamed AND content updated
        assert (tmp_path / "new_mod.py").exists()

    def test_contents_before_file_rename_import_new_mod_in_tmp_path_new_mod_py_re(
        self, tmp_path
    ):
        """Content replacement happens before file rename."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_mod.py").write_text("import old_mod\n")
        _safe_execute("old_mod", "new_mod", tmp_path)

        # File should be renamed AND content updated
        assert "import new_mod" in (tmp_path / "new_mod.py").read_text()

    def test_symlink_target_before_file_rename_os_readlink_str_link_new_target_py(
        self, tmp_path
    ):
        """Symlink targets updated before files are renamed."""
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_target.py"
        target.write_text("pass\n")
        link = tmp_path / "link.py"
        link.symlink_to("old_target.py")

        config = RenameConfig(
            pattern="old_target",
            replacement="new_target",
            directory=str(tmp_path),
            dry_run=False,
        )
        bulk_rename(config, safety_check_fn=lambda _dir: None)

        # Symlink target should point to new name
        assert os.readlink(str(link)) == "new_target.py"
        # Original file renamed

    def test_symlink_target_before_file_rename_tmp_path_new_target_py_exists(
        self, tmp_path
    ):
        """Symlink targets updated before files are renamed."""
        # Arrange
        # Act
        # Assert
        target = tmp_path / "old_target.py"
        target.write_text("pass\n")
        link = tmp_path / "link.py"
        link.symlink_to("old_target.py")

        config = RenameConfig(
            pattern="old_target",
            replacement="new_target",
            directory=str(tmp_path),
            dry_run=False,
        )
        bulk_rename(config, safety_check_fn=lambda _dir: None)

        # Symlink target should point to new name
        # Original file renamed
        assert (tmp_path / "new_target.py").exists()


# ===========================================================================
# use_sudo propagation
# ===========================================================================


class TestSudoPropagation:
    def test_config_carries_use_sudo(self):
        # Arrange
        # Act
        # Assert
        config = RenameConfig(pattern="x", replacement="y", use_sudo=True)
        assert config.use_sudo is True

    def test_preview_with_sudo_does_not_write_f_read_text_old_1_n(self, tmp_path):
        """Dry run with use_sudo should not modify the filesystem.

        We assert the contract directly: after preview_rename, the source
        file content is unchanged. Since preview goes through dry_run=True,
        no sudo runner is ever consulted — no need to spy on _sudo_run.
        """
        # Arrange
        # Act
        # Assert
        f = tmp_path / "test.py"
        f.write_text("old = 1\n")
        result = preview_rename("old", "new", directory=str(tmp_path))
        assert f.read_text() == "old = 1\n"

    def test_preview_with_sudo_does_not_write_result_dry_run_is_true(self, tmp_path):
        """Dry run with use_sudo should not modify the filesystem.

        We assert the contract directly: after preview_rename, the source
        file content is unchanged. Since preview goes through dry_run=True,
        no sudo runner is ever consulted — no need to spy on _sudo_run.
        """
        # Arrange
        # Act
        # Assert
        f = tmp_path / "test.py"
        f.write_text("old = 1\n")
        result = preview_rename("old", "new", directory=str(tmp_path))
        assert result.dry_run is True


# ===========================================================================
# Permission checking
# ===========================================================================


class TestCheckPermissions:
    """Tests for check_permissions() predicting permission-denied errors."""

    def test_writable_files_no_errors_result_permission_errors(self, tmp_path):
        """Writable files produce no permission errors."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "hello.py").write_text("old_name = 1\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))
        assert result.permission_errors == []

    def test_writable_files_no_errors_result_summary_permission_errors_0(
        self, tmp_path
    ):
        """Writable files produce no permission errors."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "hello.py").write_text("old_name = 1\n")
        result = preview_rename("old_name", "new_name", directory=str(tmp_path))
        assert result.summary["permission_errors"] == 0

    def _readonly_preview(self, tmp_path):
        """Build a preview against a read-only target file (helper)."""
        f = tmp_path / "readonly.py"
        f.write_text("old_name = 1\n")
        f.chmod(0o444)
        try:
            return preview_rename("old_name", "new_name", directory=str(tmp_path))
        finally:
            f.chmod(0o644)

    def test_readonly_file_records_a_permission_error_entry(self, tmp_path):
        # Arrange
        # Act
        result = self._readonly_preview(tmp_path)
        # Assert
        assert len(result.permission_errors) >= 1

    def test_readonly_file_permission_error_operation_is_content_replace(
        self, tmp_path
    ):
        # Arrange
        # Act
        result = self._readonly_preview(tmp_path)
        # Assert
        assert result.permission_errors[0]["operation"] == "content_replace"

    def test_readonly_file_permission_error_reason_says_file_not_writable(
        self, tmp_path
    ):
        # Arrange
        # Act
        result = self._readonly_preview(tmp_path)
        # Assert
        assert result.permission_errors[0]["reason"] == "file not writable"

    def test_readonly_file_summary_permission_errors_count_is_at_least_one(
        self, tmp_path
    ):
        # Arrange
        # Act
        result = self._readonly_preview(tmp_path)
        # Assert
        assert result.summary["permission_errors"] >= 1

    def test_readonly_parent_file_rename_detected(self, tmp_path):
        """File rename in a read-only parent directory is flagged."""
        # Arrange
        # Act
        # Assert
        subdir = tmp_path / "sub"
        subdir.mkdir()
        f = subdir / "old_name.py"
        f.write_text("content\n")
        subdir.chmod(0o555)
        try:
            result = preview_rename("old_name", "new_name", directory=str(tmp_path))
            perm_ops = [e["operation"] for e in result.permission_errors]
            assert "file_rename" in perm_ops
        finally:
            subdir.chmod(0o755)

    def test_readonly_parent_dir_rename_detected(self, tmp_path):
        """Directory rename in a read-only parent is flagged."""
        # Arrange
        # Act
        # Assert
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "old_name"
        child.mkdir()
        (child / "file.txt").write_text("data\n")
        parent.chmod(0o555)
        try:
            result = preview_rename(
                "old_name", "new_name", directory=str(tmp_path), django_safe=False
            )
            perm_ops = [e["operation"] for e in result.permission_errors]
            assert "dir_rename" in perm_ops
        finally:
            parent.chmod(0o755)

    def test_permission_errors_in_result_dataclass(self, tmp_path):
        """RenameResult.permission_errors defaults to empty list."""
        # Arrange
        # Act
        # Assert
        result = RenameResult(
            dry_run=True,
            pattern="a",
            replacement="b",
            directory=str(tmp_path),
            contents=[],
            symlink_targets=[],
            symlink_names=[],
            file_names=[],
            dir_names=[],
            summary={},
        )
        assert result.permission_errors == []

    def _check_permissions_for_readonly_file(self, tmp_path):
        """Build a check_permissions() result for a read-only file (helper)."""
        from scitex_dev.rename.safety import check_permissions

        f = tmp_path / "test.py"
        f.write_text("old = 1\n")
        f.chmod(0o444)
        try:
            result = RenameResult(
                dry_run=True,
                pattern="old",
                replacement="new",
                directory=str(tmp_path),
                contents=[{"file": str(f), "matches": 1}],
                symlink_targets=[],
                symlink_names=[],
                file_names=[],
                dir_names=[],
                summary={},
            )
            return f, check_permissions(result)
        finally:
            f.chmod(0o644)

    def test_check_permissions_returns_exactly_one_error_for_readonly_file(
        self, tmp_path
    ):
        # Arrange
        # Act
        _f, errors = self._check_permissions_for_readonly_file(tmp_path)
        # Assert
        assert len(errors) == 1

    def test_check_permissions_error_path_is_the_readonly_file(self, tmp_path):
        # Arrange
        # Act
        f, errors = self._check_permissions_for_readonly_file(tmp_path)
        # Assert
        assert errors[0]["path"] == str(f)

    def test_check_permissions_error_operation_is_content_replace(self, tmp_path):
        # Arrange
        # Act
        _f, errors = self._check_permissions_for_readonly_file(tmp_path)
        # Assert
        assert errors[0]["operation"] == "content_replace"

    def _execute_against_readonly_file(self, tmp_path):
        """Run _safe_execute against a read-only file (helper)."""
        f = tmp_path / "readonly.py"
        f.write_text("old_name = 1\n")
        f.chmod(0o444)
        try:
            return _safe_execute("old_name", "new_name", tmp_path)
        finally:
            f.chmod(0o644)

    def test_execute_blocked_by_permission_errors_sets_an_error_message(self, tmp_path):
        # Arrange
        # Act
        result = self._execute_against_readonly_file(tmp_path)
        # Assert
        assert result.error is not None

    def test_execute_blocked_by_permission_errors_message_mentions_permission_denied(
        self, tmp_path
    ):
        # Arrange
        # Act
        result = self._execute_against_readonly_file(tmp_path)
        # Assert
        assert "Permission denied" in (result.error or "")


# ===========================================================================
# Regex support
# ===========================================================================


class TestRegex:
    def test_regex_single_line_replace(self, tmp_path):
        """Regex pattern replaces single-line matches."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("old_name = 1\nold_value = 2\n")
        result = preview_rename(
            r"old_\w+", "new_thing", directory=str(tmp_path), regex=True
        )
        assert result.summary["content_matches"] == 2

    def test_regex_multiline_replace_result_summary_content_matches_1(self, tmp_path):
        """Regex with re.DOTALL matches across lines."""
        # Arrange
        # Act
        # Assert
        content = 'func(\n    next_steps=[\n        "hint1",\n        "hint2",\n    ],\n    other=True,\n)\n'
        (tmp_path / "test.py").write_text(content)
        result = preview_rename(
            r"\s*next_steps=\[.*?\],\n",
            "",
            directory=str(tmp_path),
            regex=True,
        )
        assert result.summary["content_matches"] == 1
        # Check dry-run shows before/after
        snippet = result.contents[0]["lines"][0]

    def test_regex_multiline_replace_len_result_contents_0_lines_1(self, tmp_path):
        """Regex with re.DOTALL matches across lines."""
        # Arrange
        # Act
        # Assert
        content = 'func(\n    next_steps=[\n        "hint1",\n        "hint2",\n    ],\n    other=True,\n)\n'
        (tmp_path / "test.py").write_text(content)
        result = preview_rename(
            r"\s*next_steps=\[.*?\],\n",
            "",
            directory=str(tmp_path),
            regex=True,
        )
        # Check dry-run shows before/after
        assert len(result.contents[0]["lines"]) >= 1
        snippet = result.contents[0]["lines"][0]

    def test_regex_multiline_replace_snippet_action_replace(self, tmp_path):
        """Regex with re.DOTALL matches across lines."""
        # Arrange
        # Act
        # Assert
        content = 'func(\n    next_steps=[\n        "hint1",\n        "hint2",\n    ],\n    other=True,\n)\n'
        (tmp_path / "test.py").write_text(content)
        result = preview_rename(
            r"\s*next_steps=\[.*?\],\n",
            "",
            directory=str(tmp_path),
            regex=True,
        )
        # Check dry-run shows before/after
        snippet = result.contents[0]["lines"][0]
        assert snippet["action"] == "replace"

    def test_regex_multiline_replace_next_steps_in_snippet_before(self, tmp_path):
        """Regex with re.DOTALL matches across lines."""
        # Arrange
        # Act
        # Assert
        content = 'func(\n    next_steps=[\n        "hint1",\n        "hint2",\n    ],\n    other=True,\n)\n'
        (tmp_path / "test.py").write_text(content)
        result = preview_rename(
            r"\s*next_steps=\[.*?\],\n",
            "",
            directory=str(tmp_path),
            regex=True,
        )
        # Check dry-run shows before/after
        snippet = result.contents[0]["lines"][0]
        assert "next_steps" in snippet["before"]

    def test_regex_execute_applies_substitution_new_123_in_text(self, tmp_path):
        """Regex actually modifies file content."""
        # Arrange
        # Act
        # Assert
        content = "value = old_123\nother = old_456\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute(r"old_(\d+)", r"new_\1", tmp_path, regex=True)
        text = (tmp_path / "test.py").read_text()
        assert "new_123" in text

    def test_regex_execute_applies_substitution_new_456_in_text(self, tmp_path):
        """Regex actually modifies file content."""
        # Arrange
        # Act
        # Assert
        content = "value = old_123\nother = old_456\n"
        (tmp_path / "test.py").write_text(content)
        _safe_execute(r"old_(\d+)", r"new_\1", tmp_path, regex=True)
        text = (tmp_path / "test.py").read_text()
        assert "new_456" in text

    def test_regex_backreference_preserves_groups(self, tmp_path):
        """Regex backreferences work in replacement."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("def foo_bar(): pass\n")
        _safe_execute(r"(\w+)_(\w+)", r"\2_\1", tmp_path, regex=True)
        text = (tmp_path / "test.py").read_text()
        assert "bar_foo" in text

    def test_regex_no_match(self, tmp_path):
        """Regex with no matches produces empty result."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "test.py").write_text("nothing here\n")
        result = preview_rename(
            r"nonexistent_\d+", "replacement", directory=str(tmp_path), regex=True
        )
        assert result.summary["content_matches"] == 0

    def test_regex_file_name_rename_len_result_file_names_1(self, tmp_path):
        """Regex renames file names."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_123.py").write_text("pass\n")
        result = preview_rename(
            r"old_\d+", "new_file", directory=str(tmp_path), regex=True
        )
        assert len(result.file_names) == 1

    def test_regex_file_name_rename_new_file_py_in_result_file_names_0_new_p(
        self, tmp_path
    ):
        """Regex renames file names."""
        # Arrange
        # Act
        # Assert
        (tmp_path / "old_123.py").write_text("pass\n")
        result = preview_rename(
            r"old_\d+", "new_file", directory=str(tmp_path), regex=True
        )
        assert "new_file.py" in result.file_names[0]["new_path"]

    def test_regex_multiline_block_removal_next_steps_not_in_text(self, tmp_path):
        """Real-world: remove a multiline keyword argument block."""
        # Arrange
        # Act
        # Assert
        content = """return wrap_as_mcp(
    some_func,
    side_effects=["file_create"],
    next_steps=[
        "tool_a to do X",
        "tool_b to do Y",
    ],
    idempotent=True,
)
"""
        (tmp_path / "handler.py").write_text(content)
        _safe_execute(
            r"\s*next_steps=\[.*?\],\n",
            "",
            tmp_path,
            regex=True,
        )
        text = (tmp_path / "handler.py").read_text()
        assert "next_steps" not in text

    def test_regex_multiline_block_removal_side_effects_in_text(self, tmp_path):
        """Real-world: remove a multiline keyword argument block."""
        # Arrange
        # Act
        # Assert
        content = """return wrap_as_mcp(
    some_func,
    side_effects=["file_create"],
    next_steps=[
        "tool_a to do X",
        "tool_b to do Y",
    ],
    idempotent=True,
)
"""
        (tmp_path / "handler.py").write_text(content)
        _safe_execute(
            r"\s*next_steps=\[.*?\],\n",
            "",
            tmp_path,
            regex=True,
        )
        text = (tmp_path / "handler.py").read_text()
        assert "side_effects" in text

    def test_regex_multiline_block_removal_idempotent_in_text(self, tmp_path):
        """Real-world: remove a multiline keyword argument block."""
        # Arrange
        # Act
        # Assert
        content = """return wrap_as_mcp(
    some_func,
    side_effects=["file_create"],
    next_steps=[
        "tool_a to do X",
        "tool_b to do Y",
    ],
    idempotent=True,
)
"""
        (tmp_path / "handler.py").write_text(content)
        _safe_execute(
            r"\s*next_steps=\[.*?\],\n",
            "",
            tmp_path,
            regex=True,
        )
        text = (tmp_path / "handler.py").read_text()
        assert "idempotent" in text


# EOF
