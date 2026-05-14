"""Test the RTD onboarder — codifies the 24/24-green pattern."""

from __future__ import annotations

from pathlib import Path

from scitex_dev._release.rtd_onboard import onboard_rtd


def _write_min_pyproject(repo: Path, name: str = "demo") -> None:
    (repo / "pyproject.toml").write_text(f'''[project]
name = "{name}"
version = "0.1.0"
description = "demo description"

[project.optional-dependencies]
dev = ["pytest"]
''')


def test_onboard_writes_full_tree_readthedocs_yaml_in_paths(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    assert ".readthedocs.yaml" in paths
    # docs extra appended to pyproject too


def test_onboard_writes_full_tree_conf_py_in_paths(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    assert "conf.py" in paths
    # docs extra appended to pyproject too


def test_onboard_writes_full_tree_index_rst_in_paths(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    assert "index.rst" in paths
    # docs extra appended to pyproject too


def test_onboard_writes_full_tree_api_rst_in_paths(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    assert "api.rst" in paths
    # docs extra appended to pyproject too


def test_onboard_writes_full_tree_tmp_path_pyproject_toml_in_rep_written(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    # docs extra appended to pyproject too
    assert (tmp_path / "pyproject.toml") in rep.written


def test_onboard_writes_full_tree_sphinx_rtd_theme_in_tmp_path_pyproject_t(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    # docs extra appended to pyproject too
    assert "sphinx-rtd-theme" in (tmp_path / "pyproject.toml").read_text()


def test_onboard_is_idempotent_on_second_run_rep2_written(tmp_path):
    """Re-running on a fully-onboarded repo skips every file."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    onboard_rtd(tmp_path)
    rep2 = onboard_rtd(tmp_path)
    assert rep2.written == []


def test_onboard_is_idempotent_on_second_run_len_rep2_skipped_4(tmp_path):
    """Re-running on a fully-onboarded repo skips every file."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    onboard_rtd(tmp_path)
    rep2 = onboard_rtd(tmp_path)
    assert len(rep2.skipped) == 4


def test_onboard_preserves_existing_files_custom_in_rep_skipped(tmp_path):
    """User-edited conf.py is never clobbered."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    custom = tmp_path / "docs" / "sphinx" / "conf.py"
    custom.parent.mkdir(parents=True)
    custom.write_text("# CUSTOM\n")
    rep = onboard_rtd(tmp_path)
    assert custom in rep.skipped


def test_onboard_preserves_existing_files_custom_read_text_custom_n(tmp_path):
    """User-edited conf.py is never clobbered."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    custom = tmp_path / "docs" / "sphinx" / "conf.py"
    custom.parent.mkdir(parents=True)
    custom.write_text("# CUSTOM\n")
    rep = onboard_rtd(tmp_path)
    assert custom.read_text() == "# CUSTOM\n"


def test_onboard_dry_run_rep_written(tmp_path):
    """dry_run=True records writes but doesn't touch disk."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path, dry_run=True)
    assert rep.written


def test_onboard_dry_run_not_tmp_path_readthedocs_yaml_is_file(tmp_path):
    """dry_run=True records writes but doesn't touch disk."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path, dry_run=True)
    assert not (tmp_path / ".readthedocs.yaml").is_file()


def test_onboard_dry_run_not_tmp_path_docs_sphinx_conf_py_is_file(tmp_path):
    """dry_run=True records writes but doesn't touch disk."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path, dry_run=True)
    assert not (tmp_path / "docs" / "sphinx" / "conf.py").is_file()


def test_onboard_uses_pyproject_name_and_description_my_pkg_in_index(tmp_path):
    """Generated index.rst uses the package's actual name + description."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path, name="my-pkg")
    onboard_rtd(tmp_path)
    index = (tmp_path / "docs" / "sphinx" / "index.rst").read_text()
    assert "my-pkg" in index
    conf = (tmp_path / "docs" / "sphinx" / "conf.py").read_text()


def test_onboard_uses_pyproject_name_and_description_demo_description_in_index(tmp_path):
    """Generated index.rst uses the package's actual name + description."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path, name="my-pkg")
    onboard_rtd(tmp_path)
    index = (tmp_path / "docs" / "sphinx" / "index.rst").read_text()
    assert "demo description" in index
    conf = (tmp_path / "docs" / "sphinx" / "conf.py").read_text()


def test_onboard_uses_pyproject_name_and_description_project_my_pkg_in_conf(tmp_path):
    """Generated index.rst uses the package's actual name + description."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path, name="my-pkg")
    onboard_rtd(tmp_path)
    index = (tmp_path / "docs" / "sphinx" / "index.rst").read_text()
    conf = (tmp_path / "docs" / "sphinx" / "conf.py").read_text()
    assert 'project = "my-pkg"' in conf


def test_onboard_uses_pyproject_name_and_description_from_my_pkg_import___version___in_conf(tmp_path):
    """Generated index.rst uses the package's actual name + description."""
    # Arrange
    # Act
    # Assert
    _write_min_pyproject(tmp_path, name="my-pkg")
    onboard_rtd(tmp_path)
    index = (tmp_path / "docs" / "sphinx" / "index.rst").read_text()
    conf = (tmp_path / "docs" / "sphinx" / "conf.py").read_text()
    assert "from my_pkg import __version__" in conf


def test_onboard_skips_docs_extra_if_missing_block(tmp_path):
    """If pyproject has no [project.optional-dependencies], we don't fabricate one."""
    # Arrange
    # Act
    # Assert
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
    )
    rep = onboard_rtd(tmp_path)
    # 4 files written but pyproject not touched
    assert (tmp_path / "pyproject.toml") not in rep.written
