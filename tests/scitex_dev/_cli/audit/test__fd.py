"""Tests for the Rust `fd`-backed audit file discovery helper.

No mocks: the discovery test runs the real `fd` binary against a real
temp tree; the fail-loud test really clears `fd`/`fdfind` from PATH and
asserts the loud error + install hint.
"""

from __future__ import annotations

import os
import shutil

import pytest

from scitex_dev._cli.audit._fd import (
    FD_INSTALL_HINT,
    FdNotFoundError,
    fd_binary,
    fd_find_files,
)

_HAS_FD = shutil.which("fd") is not None or shutil.which("fdfind") is not None


@pytest.fixture
def empty_path():
    """Really clear PATH so neither `fd` nor `fdfind` resolves; restore after."""
    saved = os.environ.get("PATH")
    os.environ["PATH"] = ""
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved


def test_fd_binary_raises_loudly_when_missing(empty_path):
    """A missing `fd` binary raises FdNotFoundError, never a silent fallback."""
    # Arrange
    del empty_path  # fixture clears PATH for the duration of this test
    # Act
    # Assert
    with pytest.raises(FdNotFoundError):
        fd_binary()


def test_fd_missing_error_carries_install_hint(empty_path):
    """The fail-loud error message includes the install hint."""
    # Arrange
    del empty_path  # fixture clears PATH for the duration of this test
    # Act
    try:
        fd_binary()
    except FdNotFoundError as exc:
        message = str(exc)
    else:  # pragma: no cover - the call must raise
        message = ""
    # Assert
    assert message == FD_INSTALL_HINT


def test_install_hint_names_cargo_install():
    """The install hint points at a concrete install command."""
    # Arrange
    hint = FD_INSTALL_HINT
    # Act
    has_cargo = "cargo install fd-find" in hint
    # Assert
    assert has_cargo


@pytest.mark.skipif(not _HAS_FD, reason="requires the Rust `fd` binary on PATH")
def test_fd_find_files_discovers_python_files(tmp_path):
    """fd_find_files finds every matching file recursively."""
    # Arrange
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "sub").mkdir()
    (tmp_path / "pkg" / "sub" / "b.py").write_text("y = 2\n")
    (tmp_path / "pkg" / "note.txt").write_text("ignore me\n")
    # Act
    found = {p.name for p in fd_find_files(tmp_path, glob="*.py")}
    # Assert
    assert found == {"a.py", "b.py"}


@pytest.mark.skipif(not _HAS_FD, reason="requires the Rust `fd` binary on PATH")
def test_fd_find_files_returns_sorted_paths(tmp_path):
    """Results are sorted for deterministic downstream ordering."""
    # Arrange
    for name in ("z.py", "a.py", "m.py"):
        (tmp_path / name).write_text("pass\n")
    # Act
    found = fd_find_files(tmp_path, glob="*.py")
    # Assert
    assert found == sorted(found)


@pytest.mark.skipif(not _HAS_FD, reason="requires the Rust `fd` binary on PATH")
def test_fd_find_files_honours_glob(tmp_path):
    """A non-default glob restricts the match set."""
    # Arrange
    (tmp_path / "test_one.py").write_text("pass\n")
    (tmp_path / "other.py").write_text("pass\n")
    # Act
    found = {p.name for p in fd_find_files(tmp_path, glob="test_*.py")}
    # Assert
    assert found == {"test_one.py"}


@pytest.mark.skipif(not _HAS_FD, reason="requires the Rust `fd` binary on PATH")
def test_fd_find_files_empty_for_missing_dir(tmp_path):
    """A non-existent root yields an empty list, not an error."""
    # Arrange
    missing = tmp_path / "does-not-exist"
    # Act
    found = fd_find_files(missing, glob="*.py")
    # Assert
    assert found == []
