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


def test_onboard_writes_full_tree(tmp_path):
    """Fresh repo gets all four files + docs extra appended."""
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path)
    paths = {p.name for p in rep.written}
    assert ".readthedocs.yaml" in paths
    assert "conf.py" in paths
    assert "index.rst" in paths
    assert "api.rst" in paths
    # docs extra appended to pyproject too
    assert (tmp_path / "pyproject.toml") in rep.written
    assert "sphinx-rtd-theme" in (tmp_path / "pyproject.toml").read_text()


def test_onboard_idempotent(tmp_path):
    """Re-running on a fully-onboarded repo skips every file."""
    _write_min_pyproject(tmp_path)
    onboard_rtd(tmp_path)
    rep2 = onboard_rtd(tmp_path)
    assert rep2.written == []
    assert len(rep2.skipped) == 4


def test_onboard_preserves_existing_files(tmp_path):
    """User-edited conf.py is never clobbered."""
    _write_min_pyproject(tmp_path)
    custom = tmp_path / "docs" / "sphinx" / "conf.py"
    custom.parent.mkdir(parents=True)
    custom.write_text("# CUSTOM\n")
    rep = onboard_rtd(tmp_path)
    assert custom in rep.skipped
    assert custom.read_text() == "# CUSTOM\n"


def test_onboard_dry_run(tmp_path):
    """dry_run=True records writes but doesn't touch disk."""
    _write_min_pyproject(tmp_path)
    rep = onboard_rtd(tmp_path, dry_run=True)
    assert rep.written
    assert not (tmp_path / ".readthedocs.yaml").is_file()
    assert not (tmp_path / "docs" / "sphinx" / "conf.py").is_file()


def test_onboard_uses_pyproject_name_and_description(tmp_path):
    """Generated index.rst uses the package's actual name + description."""
    _write_min_pyproject(tmp_path, name="my-pkg")
    onboard_rtd(tmp_path)
    index = (tmp_path / "docs" / "sphinx" / "index.rst").read_text()
    assert "my-pkg" in index
    assert "demo description" in index
    conf = (tmp_path / "docs" / "sphinx" / "conf.py").read_text()
    assert 'project = "my-pkg"' in conf
    assert "from my_pkg import __version__" in conf


def test_onboard_skips_docs_extra_if_missing_block(tmp_path):
    """If pyproject has no [project.optional-dependencies], we don't fabricate one."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n'
    )
    rep = onboard_rtd(tmp_path)
    # 4 files written but pyproject not touched
    assert (tmp_path / "pyproject.toml") not in rep.written
