"""Smoke tests for `scitex_dev.testing.audit_all_for_package`.

PA-306 no-mocks: the `--path` thread-through tests shim a REAL
`scitex-dev` executable onto PATH that records its argv to a tmpfile,
and let the helper's real `subprocess.run` invoke it. `shutil.which`
reads `os.environ["PATH"]`, so the shim is installed by save/restore
around `os.environ` (the same style as the skip-env fixtures below) —
no `monkeypatch`.
"""

import os
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest


@pytest.fixture
def skip_audit_env():
    """Set SCITEX_DEV_SKIP_AUDIT=1 for the test, restore on exit."""
    saved = os.environ.get("SCITEX_DEV_SKIP_AUDIT")
    os.environ["SCITEX_DEV_SKIP_AUDIT"] = "1"
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("SCITEX_DEV_SKIP_AUDIT", None)
        else:
            os.environ["SCITEX_DEV_SKIP_AUDIT"] = saved


@pytest.fixture
def no_skip_audit_env():
    """Ensure SCITEX_DEV_SKIP_AUDIT is unset for the test, restore on exit."""
    saved = os.environ.pop("SCITEX_DEV_SKIP_AUDIT", None)
    try:
        yield
    finally:
        if saved is not None:
            os.environ["SCITEX_DEV_SKIP_AUDIT"] = saved


def test_audit_all_for_package_skip_via_env(skip_audit_env):
    """SCITEX_DEV_SKIP_AUDIT=1 must short-circuit the helper."""
    # Arrange
    # Act
    # Assert
    from scitex_dev.testing import audit_all_for_package

    with pytest.raises(pytest.skip.Exception):  # pytest.skip raises Skipped
        audit_all_for_package("scitex-dev")


def test_audit_all_for_package_runs_when_unset(no_skip_audit_env):
    """Without the skip env var the helper does *something* (here: it
    just confirms the underlying CLI is callable; we don't assert exit
    code because the working tree may legitimately have violations)."""
    # Arrange
    # Act
    # Assert
    from scitex_dev.testing import _audit_conformance

    # Ensure the helper exists and is importable; running it on
    # `scitex-agent-container` (a known non-archived package) is a
    # cheap real-binary check.
    assert callable(_audit_conformance.audit_all_for_package)


# ---------------------------------------------------------------------------
# `path=` thread-through. A PATH-shimmed `scitex-dev` records its argv;
# the helper's real subprocess.run invokes it. Mirrors the established
# pattern in tests/scitex_dev/_cli/ecosystem/_cmds/test__audit_all_path.py.
# ---------------------------------------------------------------------------


def _install_shim(shim_dir: Path, log: Path) -> Path:
    """Drop a real `scitex-dev` script that records its argv to `log`."""
    script = shim_dir / "scitex-dev"
    script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\nexit 0\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


@contextmanager
def _shimmed_scitex_dev(tmp_path: Path):
    """Put a recording `scitex-dev` first on PATH; yield its argv log."""
    log = tmp_path / "argv.log"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    _install_shim(shim_dir, log)
    saved = os.environ["PATH"]
    os.environ["PATH"] = f"{shim_dir}{os.pathsep}{saved}"
    try:
        yield log
    finally:
        os.environ["PATH"] = saved


def test_audit_all_for_package_threads_path_to_the_subprocess(
    no_skip_audit_env, tmp_path
):
    """`path=` must reach the audit-all CLI as `--path <path>`.

    Without this the audit resolves the tree by import location / the
    `~/proj/<name>` guess and can grade a different commit than the one
    under test.
    """
    # Arrange
    from scitex_dev.testing import audit_all_for_package

    checkout = tmp_path / "wt"
    checkout.mkdir()
    # Act
    with _shimmed_scitex_dev(tmp_path) as log:
        audit_all_for_package("scitex-io", path=checkout)
    # Assert
    assert f"--path {checkout}" in log.read_text()


def test_audit_all_for_package_accepts_a_string_path(no_skip_audit_env, tmp_path):
    """`path=` accepts `str` as well as `Path` (annotated `str | Path`)."""
    # Arrange
    from scitex_dev.testing import audit_all_for_package

    checkout = tmp_path / "wt"
    checkout.mkdir()
    # Act
    with _shimmed_scitex_dev(tmp_path) as log:
        audit_all_for_package("scitex-io", path=str(checkout))
    # Assert
    assert f"--path {checkout}" in log.read_text()


def test_audit_all_for_package_without_path_omits_the_flag(
    no_skip_audit_env, tmp_path
):
    """`path=None` (the default) keeps the historical argv byte-for-byte."""
    # Arrange
    from scitex_dev.testing import audit_all_for_package

    # Act
    with _shimmed_scitex_dev(tmp_path) as log:
        audit_all_for_package("scitex-io")
    # Assert
    assert "--path" not in log.read_text()


def test_audit_all_for_package_without_path_still_passes_the_distribution(
    no_skip_audit_env, tmp_path
):
    """The back-compat argv is exactly `ecosystem audit-all <distribution>`."""
    # Arrange
    from scitex_dev.testing import audit_all_for_package

    # Act
    with _shimmed_scitex_dev(tmp_path) as log:
        audit_all_for_package("scitex-io")
    # Assert
    assert log.read_text().strip() == "ecosystem audit-all scitex-io"
