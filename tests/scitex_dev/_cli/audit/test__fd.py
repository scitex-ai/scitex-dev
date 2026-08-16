"""Tests for the Rust `fd`-backed audit file discovery helper.

No mocks: the discovery test runs the real `fd` binary against a real
temp tree; the fail-loud tests really clear PATH so `fd`/`fdfind` cannot
resolve and assert the loud error + install hint; the fallback tests
really clear PATH and assert the stdlib walk still discovers files AND
announces loudly (warns) by default, or raises under the strict
`require_fd` knob.
"""

from __future__ import annotations

import os
import shutil
import warnings

import pytest

from scitex_dev._cli.audit._fd import (
    FD_FALLBACK_WARNING,
    FD_INSTALL_HINT,
    FdNotFoundError,
    fd_available,
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


@pytest.fixture
def path_without_fd():
    """Really clear PATH so neither `fd` nor `fdfind` resolves; restore after.

    Reproduces the GitHub `ubuntu-latest` situation where `fd` is absent.
    Dir-level stripping is unreliable when `fd`/`fdfind` lives in a system
    dir reachable via more than one PATH entry (e.g. `/bin` → `/usr/bin`
    symlink on Debian, where the CI `fd-find` package installs `fdfind`),
    so we clear PATH outright. The fd-absent codepath (`_rglob_find_files`
    + config reads) is pure stdlib and never shells out, so an empty PATH
    is safe here.
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


def test_fd_binary_raises_loudly_when_missing(empty_path):
    """A missing `fd` binary raises FdNotFoundError, never a silent fallback."""
    # Arrange
    del empty_path  # fixture clears PATH for the duration of this test
    # Act
    ctx = pytest.raises(FdNotFoundError)
    # Assert
    with ctx:
        fd_binary()


def test_fd_missing_error_carries_install_hint(empty_path):
    """The fail-loud error message includes the install hint."""
    # Arrange
    del empty_path  # fixture clears PATH for the duration of this test
    try:
        fd_binary()
    except FdNotFoundError as exc:
        message = str(exc)
    else:  # pragma: no cover - the call must raise
        message = ""
    # Act
    # (message captured above)
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


def test_fd_available_returns_none_without_fd(path_without_fd):
    """fd_available reports None when neither fd nor fdfind is on PATH."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    # Act
    resolved = fd_available()
    # Assert
    assert resolved is None


def test_fd_find_files_warns_loudly_on_fallback(path_without_fd, tmp_path):
    """With fd absent (default), the fallback announces loudly via a warning."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "a.py").write_text("x = 1\n")
    # Act
    ctx = pytest.warns(RuntimeWarning, match="falling back to the stdlib scan")
    # Assert
    with ctx:
        fd_find_files(tmp_path, glob="*.py")


def test_the_fallback_warning_is_framed_as_correctness_not_speed(
    path_without_fd, tmp_path
):
    """THE WORDING IS THE FEATURE, so it gets a test.

    The old text read "falling back to slower stdlib scan; install fd for
    speed". Every word true; the consequence named was wrong. It fired
    correctly in CI on 2026-08-15 while the fallback was grading a
    different set of files, and every reader — me included — filed it
    under performance. A warning that misdescribes its own consequence is
    worse than silence, because it is actively read and dismissed.
    """
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "a.py").write_text("x = 1\n")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fd_find_files(tmp_path, glob="*.py")
    message = str(caught[0].message) if caught else ""
    # Act
    frames_as_correctness = "CORRECTNESS" in message
    # Assert
    assert frames_as_correctness


def test_fd_fallback_warning_message_advises_install(path_without_fd, tmp_path):
    """The fallback warning still tells the reader how to install fd.

    Reframing the warning from speed to correctness must not cost the
    actionable half: an alarm nobody can act on is one people learn to
    skip, which is how the old one died.
    """
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "a.py").write_text("x = 1\n")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fd_find_files(tmp_path, glob="*.py")
    message = str(caught[0].message) if caught else ""
    # Act
    advises_install = "apt install fd-find" in message
    # Assert
    assert advises_install


def test_fd_find_files_falls_back_without_fd(path_without_fd, tmp_path):
    """With fd absent, fd_find_files still discovers files via the stdlib walk."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "pkg" / "sub").mkdir()
    (tmp_path / "pkg" / "sub" / "b.py").write_text("y = 2\n")
    (tmp_path / "pkg" / "note.txt").write_text("ignore me\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        found = {p.name for p in fd_find_files(tmp_path, glob="*.py")}
    # Act
    # (discovery captured above; warning intentionally suppressed here —
    #  the loud-warning contract is covered by the dedicated warn test)
    # Assert
    assert found == {"a.py", "b.py"}


def test_fd_find_files_fallback_honours_glob(path_without_fd, tmp_path):
    """The stdlib fallback respects a non-default glob, matching the fd path."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "test_one.py").write_text("pass\n")
    (tmp_path / "other.py").write_text("pass\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        found = {p.name for p in fd_find_files(tmp_path, glob="test_*.py")}
    # Act
    # (discovery captured above)
    # Assert
    assert found == {"test_one.py"}


def test_fd_find_files_fallback_returns_sorted_paths(path_without_fd, tmp_path):
    """The stdlib fallback returns sorted paths for deterministic ordering."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    for name in ("z.py", "a.py", "m.py"):
        (tmp_path / name).write_text("pass\n")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        found = fd_find_files(tmp_path, glob="*.py")
    # Act
    # (discovery captured above)
    # Assert
    assert found == sorted(found)


def test_fd_find_files_does_not_raise_without_fd_by_default(path_without_fd, tmp_path):
    """A missing fd binary degrades gracefully by default — no FdNotFoundError."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "a.py").write_text("pass\n")
    raised = None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fd_find_files(tmp_path, glob="*.py")
        except FdNotFoundError as exc:  # pragma: no cover - regression guard
            raised = exc
    # Act
    # (capture above)
    # Assert
    assert raised is None


def test_fd_find_files_raises_when_require_fd_and_absent(path_without_fd, tmp_path):
    """With require_fd=True and fd absent, fd_find_files fails loud (strict knob)."""
    # Arrange
    del path_without_fd  # fixture strips fd dirs for the duration of this test
    (tmp_path / "a.py").write_text("pass\n")
    # Act
    ctx = pytest.raises(FdNotFoundError)
    # Assert
    with ctx:
        fd_find_files(tmp_path, glob="*.py", require_fd=True)


@pytest.mark.skipif(not _HAS_FD, reason="requires the Rust `fd` binary on PATH")
def test_fd_find_files_require_fd_uses_fd_when_present(tmp_path):
    """With require_fd=True and fd present, discovery still works (no raise)."""
    # Arrange
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    # Act
    found = {p.name for p in fd_find_files(tmp_path, glob="*.py", require_fd=True)}
    # Assert
    assert found == {"a.py", "b.py"}
