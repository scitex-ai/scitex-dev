"""Tests for the PS-204 orphan-test hinter.

Real tree, no mocks: builds an actual `src/<pkg>/` layout under `tmp_path`
and asserts the hinter's same-basename match. The regression guards run
the hinter with `fd`/`fdfind` stripped from PATH (the GitHub `ubuntu-latest`
situation) and assert it (a) by default warns loudly + still indexes the
src tree via the stdlib walk, and (b) under the `audit.require-fd` strict
knob raises `FdNotFoundError` instead of falling back.
"""

from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path

import pytest

from scitex_dev._cli.audit._fd import FdNotFoundError
from scitex_dev._cli.audit._project._check_orphan_hint import (
    build_orphan_hinter,
    is_require_fd,
)

_HAS_FD = shutil.which("fd") is not None or shutil.which("fdfind") is not None


@pytest.fixture
def path_without_fd():
    """Really clear PATH so neither `fd` nor `fdfind` resolves; restore after.

    Reproduces the GitHub `ubuntu-latest` runner where `fd` is absent.
    Dir-level stripping is unreliable when `fd`/`fdfind` lives in a system
    dir reachable via more than one PATH entry (e.g. `/bin` → `/usr/bin`
    symlink on Debian, where the CI `fd-find` package installs `fdfind`),
    so we clear PATH outright. The hinter's fd-absent codepath (stdlib
    walk + config reads) never shells out, so an empty PATH is safe here.
    """
    saved = os.environ.get("PATH")
    os.environ["PATH"] = ""
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved


def _make_project(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal repo with a moved src file; return (repo, src_pkg)."""
    repo = tmp_path / "myrepo"
    src_pkg = repo / "src" / "mypkg"
    (src_pkg / "_cli").mkdir(parents=True)
    (src_pkg / "__init__.py").write_text("\n")
    (src_pkg / "_cli" / "__init__.py").write_text("\n")
    # The src file lives under _cli/ — a test mirroring the old flat layout
    # is therefore orphaned and should be hinted toward this location.
    (src_pkg / "_cli" / "audit.py").write_text("def audit():\n    return 0\n")
    return repo, src_pkg


def test_orphan_hinter_suggests_moved_src_with_fd(tmp_path):
    """With fd present, the hinter points an orphan test at the moved src file."""
    # Arrange
    repo, src_pkg = _make_project(tmp_path)
    hint = build_orphan_hinter(src_pkg, repo)
    # Act
    detail = hint(Path("test_audit.py"))
    # Assert
    assert "src/mypkg/_cli/audit.py" in detail


def test_orphan_hinter_suggests_moved_src_without_fd(path_without_fd, tmp_path):
    """With fd absent, the hinter still resolves the moved src via stdlib walk."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    repo, src_pkg = _make_project(tmp_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        hint = build_orphan_hinter(src_pkg, repo)
        detail = hint(Path("test_audit.py"))
    # Act
    # (hint built + invoked above; loud-warning contract covered separately)
    # Assert
    assert "src/mypkg/_cli/audit.py" in detail


def test_orphan_hinter_warns_loudly_without_fd(path_without_fd, tmp_path):
    """Building the hinter without fd announces the fallback loudly (warns)."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    repo, src_pkg = _make_project(tmp_path)
    # Act
    ctx = pytest.warns(RuntimeWarning, match="falling back to slower stdlib")
    # Assert
    with ctx:
        build_orphan_hinter(src_pkg, repo)


def test_orphan_hinter_does_not_crash_without_fd(path_without_fd, tmp_path):
    """Building the hinter without fd degrades gracefully — no hard crash."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    repo, src_pkg = _make_project(tmp_path)
    raised = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            build_orphan_hinter(src_pkg, repo)
        except Exception as exc:  # pragma: no cover - regression guard
            raised = exc
    # Act
    # (capture above)
    # Assert
    assert raised is None


def test_orphan_hinter_raises_without_fd_when_require_fd_yaml(
    path_without_fd, tmp_path
):
    """With `audit.require-fd: true` in config and fd absent, the hinter fails loud."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    repo, src_pkg = _make_project(tmp_path)
    cfg_dir = repo / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text("audit:\n  require-fd: true\n")
    # Act
    ctx = pytest.raises(FdNotFoundError)
    # Assert
    with ctx:
        build_orphan_hinter(src_pkg, repo)


def test_is_require_fd_reads_yaml_config(tmp_path):
    """is_require_fd returns True when config.yaml sets audit.require-fd: true."""
    # Arrange
    repo = tmp_path / "repo"
    cfg_dir = repo / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text("audit:\n  require-fd: true\n")
    # Act
    enabled = is_require_fd(repo)
    # Assert
    assert enabled is True


def test_is_require_fd_reads_pyproject_tool_block(tmp_path):
    """is_require_fd returns True for [tool.scitex_dev] audit.require_fd = true."""
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[tool.scitex_dev]\naudit.require_fd = true\n")
    # Act
    enabled = is_require_fd(repo)
    # Assert
    assert enabled is True


def test_is_require_fd_false_without_opt_in(tmp_path):
    """is_require_fd returns False when neither config nor pyproject opts in."""
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[tool.scitex_dev]\n")
    # Act
    enabled = is_require_fd(repo)
    # Assert
    assert enabled is False
