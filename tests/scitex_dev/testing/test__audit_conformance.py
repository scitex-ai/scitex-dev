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
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from scitex_dev.testing import _audit_conformance as conformance


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
        # No launcher: the skip short-circuits BEFORE any subprocess, so
        # naming an auditor here would imply this test reaches one.
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



def _shimmed_launcher(tmp_path: Path) -> list[str]:
    """The auditor these tests mean, named OUT LOUD.

    These tests used to select their auditor by planting a shim first on
    PATH — which worked only BECAUSE `audit_all_for_package` resolved
    through `shutil.which`. That resolution was the defect (sac, P1,
    2026-08-18: local and CI graded against different rule corpora with
    no code difference), and removing it necessarily removes the tests'
    smuggling route too.

    PATH is still shimmed by the fixtures, deliberately: if the helper
    ever consults it again, these tests keep working and the dedicated
    hostile-PATH test in `test__auditor_comes_from_the_env_under_test.py`
    is the one that fails. Naming the launcher here is the honest form —
    a test should say which binary it means rather than arrange for the
    environment to answer.
    """
    return [str(tmp_path / "bin" / "scitex-dev")]

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
        audit_all_for_package(
            "scitex-io", path=checkout, launcher=_shimmed_launcher(tmp_path)
        )
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
        audit_all_for_package(
            "scitex-io", path=str(checkout), launcher=_shimmed_launcher(tmp_path)
        )
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
        audit_all_for_package(
            "scitex-io", launcher=_shimmed_launcher(tmp_path)
        )
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
        audit_all_for_package(
            "scitex-io", launcher=_shimmed_launcher(tmp_path)
        )
    # Assert
    assert log.read_text().strip() == "ecosystem audit-all scitex-io"


# ---------------------------------------------------------------------------
# THE AUDITOR COMES FROM THE INTERPRETER UNDER TEST, NOT FROM PATH.
#
# sac's P1, measured on scitex-compute-04 2026-08-18: same tree, same
# command, auditor 0.49.2 reported PS-226 while auditor 0.54.0 reported
# PS-140, PS-226, PS-231 — and the interpreter running pytest carried
# 0.54.0 throughout. The PATH entry resolved through a bash wrapper into
# a DIFFERENT PACKAGE's venv, so one repo's test result depended on
# another repo's environment.
#
# These live here rather than in a file of their own because the
# behaviour belongs to `_audit_conformance`; a separate test module would
# be an orphan with no src file to mirror (PS-204).
# ---------------------------------------------------------------------------

def test_the_helper_launches_the_interpreter_under_test(monkeypatch, tmp_path) -> None:
    """Behavioural, not textual.

    My first version of this grepped the source for
    `shutil.which("scitex-dev")` and asserted it absent — and FAILED,
    because the explanatory comment above the fix quotes the old code.
    A predicate that matches the ARTIFACT (a string anywhere in the
    file) rather than the THING (a live call site) is the same defect
    this whole card is about, committed while writing a test about
    precision. So: capture the argv actually handed to subprocess.
    """
    # Arrange
    seen: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(argv, **kw):
        seen["argv"] = argv
        return _Proc()

    monkeypatch.setattr(conformance.subprocess, "run", _fake_run)
    # Act
    conformance.audit_all_for_package("scitex-dev", path=tmp_path)
    # Assert
    assert seen["argv"][:3] == [sys.executable, "-m", "scitex_dev"]


def test_the_helper_ignores_a_hostile_binary_on_PATH(monkeypatch, tmp_path) -> None:
    """PATH must not be consulted at all.

    Verified end to end as well: with a fake `scitex-dev` planted first
    on PATH that exits 3 and prints a marker, the real gate runs its
    full six-sub-auditor sweep (25s) and passes — the impostor is never
    executed.
    """
    # Arrange
    seen: dict = {}

    class _Proc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(
        conformance.shutil, "which", lambda *_a, **_k: "/tmp/hostile/scitex-dev"
    )
    monkeypatch.setattr(
        conformance.subprocess, "run", lambda argv, **kw: (seen.__setitem__("argv", argv), _Proc())[1]
    )
    # Act
    conformance.audit_all_for_package("scitex-dev", path=tmp_path)
    # Assert
    assert "/tmp/hostile/scitex-dev" not in seen["argv"]


def test_the_subauditor_fanout_uses_the_same_interpreter() -> None:
    """THE LAYER THAT ACTUALLY DECIDES THE RULE CORPUS.

    Fixing only the outer helper leaves every sub-auditor resolving from
    PATH — which is where sac's measurement came from, and which my own
    first fix missed while every visible signal said it was done.
    """
    # Arrange
    from scitex_dev._cli.ecosystem._cmds import _audit_all

    # Act
    builds_from_interpreter = "scitex_dev_argv = [_sys.executable" in Path(
        _audit_all.__file__
    ).read_text()
    # Assert
    assert builds_from_interpreter


def test_the_identity_line_reports_that_launcher() -> None:
    """Otherwise the report names a version nothing measured with."""
    # Arrange
    from scitex_dev.testing._auditor_identity import auditor_identity

    # Act
    identity = auditor_identity([sys.executable, "-m", "scitex_dev"])
    # Assert
    assert "-m scitex_dev" in identity


# EOF
