"""Tests for the ecosystem dashboard state layer."""

from __future__ import annotations

import dataclasses


def test_package_state_is_a_dataclass_with_expected_fields_dataclasses_is_dataclass_packagestate():
    """`PackageState` is the data shape every dashboard cell consumes.
    Verify it's a dataclass with the fields the renderer reads, so
    accidental field renames break this test instead of silently
    producing empty cells."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    assert dataclasses.is_dataclass(PackageState)
    field_names = {f.name for f in dataclasses.fields(PackageState)}
    # Minimum surface the renderer consumes today.


def test_package_state_is_a_dataclass_with_expected_fields_pkg_in_field_names():
    """`PackageState` is the data shape every dashboard cell consumes.
    Verify it's a dataclass with the fields the renderer reads, so
    accidental field renames break this test instead of silently
    producing empty cells."""
    # Arrange
    # Act
    # Assert
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    field_names = {f.name for f in dataclasses.fields(PackageState)}
    # Minimum surface the renderer consumes today.
    assert "pkg" in field_names


def test_gather_ecosystem_state_returns_a_list():
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state

    # Act
    states = gather_ecosystem_state(verbosity=0)
    # Assert
    assert isinstance(states, list)


def test_gather_ecosystem_state_elements_are_PackageState():
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state
    from scitex_dev._cli.ecosystem._dashboard._state import PackageState

    # Act
    states = gather_ecosystem_state(verbosity=0)
    # Assert
    assert all(isinstance(s, PackageState) for s in states)


def test_gather_ecosystem_state_elements_have_pkg_field():
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard import gather_ecosystem_state

    # Act
    states = gather_ecosystem_state(verbosity=0)
    # Assert
    assert all(hasattr(s, "pkg") for s in states)


# ---------------------------------------------------------------------------
# _enrich_gh_release coverage — drives the 2026-05-27 RELEASE column via a
# real fake `gh` binary on PATH (per STX-NM002 the test must not mock; we
# use the "real subprocess against a fixture script" recipe documented in
# `_skills/general/02_package/12_no-mocks.md`).
# ---------------------------------------------------------------------------


def _install_fake_gh(
    bin_dir: "object",
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
) -> None:
    """Drop an executable `gh` shell script into ``bin_dir``.

    The script ignores its CLI args, prints ``stdout`` / ``stderr``,
    and exits with ``exit_code``. Used to exercise `_enrich_gh_release`
    without touching the real GitHub CLI (which may not be installed,
    or may be authenticated against the wrong account in CI).
    """
    import os
    import stat
    from pathlib import Path as _Path

    bin_dir = _Path(bin_dir)
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "gh"
    # Heredoc-safe quoting: `printf %s` reads each blob from an env var
    # rather than embedding it in the script body, so funky quotes in
    # the test inputs don't break the shell.
    # `#!/bin/sh` (absolute path) survives a PATH-stripped environment;
    # `#!/usr/bin/env bash` would fail to find `bash` once PATH is
    # replaced with a single-entry test bin dir.
    script.write_text(
        "#!/bin/sh\n"
        'printf %s "${FAKE_GH_STDOUT-}"\n'
        'printf %s "${FAKE_GH_STDERR-}" >&2\n'
        'exit "${FAKE_GH_EXIT-0}"\n'
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    os.environ["FAKE_GH_STDOUT"] = stdout
    os.environ["FAKE_GH_STDERR"] = stderr
    os.environ["FAKE_GH_EXIT"] = str(exit_code)


def _swap_path_to(bin_dir: "object") -> str:
    """Replace ``$PATH`` so only ``bin_dir`` is visible. Returns the
    previous PATH so callers can restore it in a ``finally`` block."""
    import os

    saved = os.environ.get("PATH", "")
    os.environ["PATH"] = str(bin_dir)
    return saved


def _restore_env(path_value: str) -> None:
    """Restore ``$PATH`` and drop the FAKE_GH_* test scaffolding."""
    import os

    os.environ["PATH"] = path_value
    for k in ("FAKE_GH_STDOUT", "FAKE_GH_STDERR", "FAKE_GH_EXIT"):
        os.environ.pop(k, None)


def test_enrich_gh_release_populates_tag_on_success(tmp_path):
    """The happy path: `gh release view` returns a JSON object with
    `tagName`; the enricher copies the tag into `gh_release_latest`."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="scitex-foo", exists_locally=True)
    _install_fake_gh(
        tmp_path / "bin",
        stdout='{"tagName": "v0.1.0"}\n',
        exit_code=0,
    )
    saved = _swap_path_to(tmp_path / "bin")
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_latest == "v0.1.0"


def test_enrich_gh_release_sets_lookup_done_on_success(tmp_path):
    """A successful query must flip `gh_release_lookup_done` so the
    renderer knows the cell is final (not a pending lookup)."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="scitex-foo", exists_locally=True)
    _install_fake_gh(
        tmp_path / "bin",
        stdout='{"tagName": "v0.1.0"}\n',
        exit_code=0,
    )
    saved = _swap_path_to(tmp_path / "bin")
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_lookup_done is True


def test_enrich_gh_release_flags_release_not_found_as_lookup_done(tmp_path):
    """`gh release view` exits 1 with `release not found` on stderr
    when no release exists yet. That's a confirmed-negative answer —
    the renderer must show MISSING, not the pending-N/C placeholder,
    so `gh_release_lookup_done` must flip to True."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="crossref-local", exists_locally=True)
    _install_fake_gh(
        tmp_path / "bin",
        stderr="release not found\n",
        exit_code=1,
    )
    saved = _swap_path_to(tmp_path / "bin")
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_lookup_done is True


def test_enrich_gh_release_leaves_tag_empty_when_release_not_found(tmp_path):
    """Symmetric to the previous test — the "no release" branch
    must NOT manufacture a fake tag; gh_release_latest stays empty
    so the renderer can show MISSING."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="crossref-local", exists_locally=True)
    _install_fake_gh(
        tmp_path / "bin",
        stderr="release not found\n",
        exit_code=1,
    )
    saved = _swap_path_to(tmp_path / "bin")
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_latest == ""


def test_enrich_gh_release_transport_failure_leaves_lookup_pending(tmp_path):
    """Any unrecognised non-zero exit (auth failure, rate limit,
    network drop, etc.) MUST leave `gh_release_lookup_done` False so
    the renderer keeps showing N/C — a transient error must not be
    confused with a confirmed missing release."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="scitex-foo", exists_locally=True)
    _install_fake_gh(
        tmp_path / "bin",
        stderr="HTTP 502 Bad Gateway\n",
        exit_code=1,
    )
    saved = _swap_path_to(tmp_path / "bin")
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_lookup_done is False


def test_enrich_gh_release_invalid_json_leaves_lookup_pending(tmp_path):
    """If `gh` returns rc=0 but the body isn't valid JSON, treat it
    as a transient parse failure — leave the lookup pending so a
    later run can retry."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="scitex-foo", exists_locally=True)
    _install_fake_gh(
        tmp_path / "bin",
        stdout="not-json-at-all\n",
        exit_code=0,
    )
    saved = _swap_path_to(tmp_path / "bin")
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_lookup_done is False


def test_enrich_gh_release_skips_when_package_not_local():
    """No subprocess should run when the package isn't checked out
    locally — the cheap early-return path keeps the bulk enricher
    from spending a `gh` call per unknown repo."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="not-checked-out", exists_locally=False)
    # Act
    _enrich_gh_release(state)
    # Assert
    assert state.gh_release_lookup_done is False


def test_enrich_gh_release_handles_missing_gh_binary(tmp_path):
    """When `gh` isn't on PATH at all, the enricher must swallow the
    FileNotFoundError and leave the lookup pending (renderer shows
    N/C). Reproducing the bare-container case where the GitHub CLI
    simply isn't installed."""
    # Arrange
    from scitex_dev._cli.ecosystem._dashboard._state import (
        PackageState,
        _enrich_gh_release,
    )

    state = PackageState(pkg="scitex-foo", exists_locally=True)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    saved = _swap_path_to(empty_bin)
    # Act
    try:
        _enrich_gh_release(state)
    finally:
        _restore_env(saved)
    # Assert
    assert state.gh_release_lookup_done is False
