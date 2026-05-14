"""Unit tests for scitex_dev._creds._rotate."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from scitex_dev._creds._rotate import (
    rotate_all,
    validate_source,
)


# -------- gh shim helpers ------------------------------------------------


def _install_gh_shim(
    bin_dir: Path,
    *,
    remote_sha: str | None = None,
    set_secret_ok: bool = True,
    set_var_ok: bool = True,
) -> Path:
    """Create an executable `gh` shim at ``bin_dir/gh`` and a call-log file.

    The shim dispatches on ``$1 $2`` (e.g. ``variable get``, ``secret set``,
    ``variable set``) and appends one short token per call to the log so
    tests can assert how many times each verb was invoked.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    log = bin_dir / "calls.log"
    log.write_text("")
    sha = remote_sha if remote_sha is not None else ""
    var_get_rc = 0 if remote_sha is not None else 1
    secret_set_rc = 0 if set_secret_ok else 1
    var_set_rc = 0 if set_var_ok else 1
    script = f"""#!/usr/bin/env bash
verb="$1 $2"
case "$verb" in
  "variable get")
    echo "var_get" >> "{log}"
    [ {var_get_rc} -eq 0 ] && echo "{sha}"
    exit {var_get_rc};;
  "secret set")
    echo "secret" >> "{log}"
    exit {secret_set_rc};;
  "variable set")
    echo "var_set" >> "{log}"
    exit {var_set_rc};;
  *)
    exit 0;;
esac
"""
    gh = bin_dir / "gh"
    gh.write_text(script)
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    # Also stage a noop `git` so `_detect_repo_for_package` falls back to
    # the registry rather than trying the real git on PATH.
    git = bin_dir / "git"
    git.write_text("#!/usr/bin/env bash\nexit 1\n")
    git.chmod(git.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return log


def _count_calls(log: Path) -> dict[str, int]:
    counts = {"secret": 0, "var_get": 0, "var_set": 0}
    if log.exists():
        for line in log.read_text().splitlines():
            line = line.strip()
            if line in counts:
                counts[line] += 1
    return counts


@pytest.fixture
def gh_env(tmp_path):
    """Yield a path-builder for installing gh shims with a clean PATH.

    Returns a function ``install(...)`` that places a shim and returns the
    call-log path. Restores PATH on exit.
    """
    bin_dir = tmp_path / "bin"
    saved_path = os.environ.get("PATH")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{saved_path}"

    def install(**kwargs):
        return _install_gh_shim(bin_dir, **kwargs)

    try:
        yield install
    finally:
        if saved_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved_path


# -------- helpers --------------------------------------------------------

_GOOD_PAYLOAD = {
    "claudeAiOauth": {
        "accessToken": "sk-ant-oat01-fake",
        "refreshToken": "rt-fake",
        "expiresAt": 9_999_999_999_999,  # far future, ms-epoch
    }
}


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "creds.json"
    p.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return p


# -------- validate_source -----------------------------------------------


def test_validate_source_returns_state_on_good_file_state_is_not_none(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(p)
    assert state is not None


def test_validate_source_returns_state_on_good_file_state_sha256(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(p)
    assert state.sha256


def test_validate_source_returns_state_on_good_file_state_byte_count_len_p_read_text_encode(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(p)
    assert state.byte_count == len(p.read_text().encode("utf-8"))


def test_validate_source_missing_file_silent(tmp_path):
    # Arrange
    # Act
    # Assert
    assert validate_source(tmp_path / "no.json") is None


def test_validate_source_parse_error_raises(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, "{not json")
    with pytest.raises(ValueError):
        validate_source(p)


def test_validate_source_missing_oauth_key_raises(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, {"foo": "bar"})
    with pytest.raises(ValueError):
        validate_source(p)


def test_validate_source_expired_silent_ms(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, {"claudeAiOauth": {"expiresAt": 1_000}})
    assert validate_source(p, now_ms=lambda: 2_000_000_000_000) is None


def test_validate_source_expired_silent_seconds(tmp_path):
    # Arrange
    # Act
    # Assert
    p = _write(tmp_path, {"claudeAiOauth": {"expires_at": 100}})
    assert validate_source(p, now_ms=lambda: 2_000_000_000_000) is None


# -------- rotate_all (real subprocess against a `gh` shim on PATH) -------


_ONE_PKG = {"scitex-io": {"github_repo": "ywatanabe1989/scitex-io"}}
_NO_LOCAL = lambda _: None  # noqa: E731 — short, single-use


def test_rotate_all_sha_match_skips_gh_len_results_1(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    log = gh_env(remote_sha=state.sha256)

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert len(results) == 1


def test_rotate_all_sha_match_skips_gh_results_0_status_unchanged(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    log = gh_env(remote_sha=state.sha256)

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert results[0].status == "unchanged"


def test_rotate_all_sha_match_skips_gh_calls_secret_0(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    log = gh_env(remote_sha=state.sha256)

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["secret"] == 0


def test_rotate_all_sha_match_skips_gh_calls_var_set_0(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    log = gh_env(remote_sha=state.sha256)

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["var_set"] == 0


def test_rotate_all_sha_mismatch_rotates_results_0_status_rotated(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    log = gh_env(remote_sha="deadbeef")

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert results[0].status == "rotated"


def test_rotate_all_sha_mismatch_rotates_calls_secret_1(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    log = gh_env(remote_sha="deadbeef")

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["secret"] == 1


def test_rotate_all_sha_mismatch_rotates_calls_var_set_1(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    log = gh_env(remote_sha="deadbeef")

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["var_set"] == 1


def test_rotate_all_missing_remote_skipped_results_0_status_skipped(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    gh_env()
    eco = {"phantom-pkg": {}}  # no github_repo

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=eco,
        local_path_lookup=_NO_LOCAL,
    )
    assert results[0].status == "skipped"


def test_rotate_all_missing_remote_skipped_no_remote_in_results_0_message(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    gh_env()
    eco = {"phantom-pkg": {}}  # no github_repo

    results = rotate_all(
        source_path=src,
        dry_run=False,
        ecosystem=eco,
        local_path_lookup=_NO_LOCAL,
    )
    assert "no remote" in results[0].message


def test_rotate_all_json_parse_error_raises(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, "{nope")
    gh_env()
    with pytest.raises(ValueError):
        rotate_all(source_path=src)


def test_rotate_all_missing_oauth_raises(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, {"foo": "bar"})
    gh_env()
    with pytest.raises(ValueError):
        rotate_all(source_path=src)


def test_rotate_all_expired_token_silent(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, {"claudeAiOauth": {"expiresAt": 1}})
    gh_env()
    # Should return empty list — no per-repo activity.
    assert rotate_all(source_path=src) == []


def test_rotate_all_dry_run_makes_no_gh_set_results_0_status_dry_run(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    log = gh_env(remote_sha="deadbeef")

    results = rotate_all(
        source_path=src,
        dry_run=True,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert results[0].status == "dry-run"


def test_rotate_all_dry_run_makes_no_gh_set_calls_secret_0(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    log = gh_env(remote_sha="deadbeef")

    results = rotate_all(
        source_path=src,
        dry_run=True,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["secret"] == 0


def test_rotate_all_dry_run_makes_no_gh_set_calls_var_set_0(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    log = gh_env(remote_sha="deadbeef")

    results = rotate_all(
        source_path=src,
        dry_run=True,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["var_set"] == 0


def test_rotate_all_force_overrides_match_results_0_status_rotated(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    log = gh_env(remote_sha=state.sha256)

    results = rotate_all(
        source_path=src,
        dry_run=False,
        force=True,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert results[0].status == "rotated"


def test_rotate_all_force_overrides_match_calls_secret_1(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    log = gh_env(remote_sha=state.sha256)

    results = rotate_all(
        source_path=src,
        dry_run=False,
        force=True,
        ecosystem=_ONE_PKG,
        local_path_lookup=_NO_LOCAL,
    )
    calls = _count_calls(log)
    assert calls["secret"] == 1


def test_rotate_all_only_and_exclude_filters_r_package_for_r_in_only_pkg_a(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    gh_env(remote_sha="x")
    eco = {
        "pkg-a": {"github_repo": "o/a"},
        "pkg-b": {"github_repo": "o/b"},
        "pkg-c": {"github_repo": "o/c"},
    }
    only = rotate_all(
        source_path=src,
        only=["pkg-a"],
        dry_run=True,
        ecosystem=eco,
        local_path_lookup=_NO_LOCAL,
    )
    assert [r.package for r in only] == ["pkg-a"]
    excluded = rotate_all(
        source_path=src,
        exclude=["pkg-b"],
        dry_run=True,
        ecosystem=eco,
        local_path_lookup=_NO_LOCAL,
    )


def test_rotate_all_only_and_exclude_filters_r_package_for_r_in_excluded_pkg_a_pkg_c(tmp_path, gh_env):
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    gh_env(remote_sha="x")
    eco = {
        "pkg-a": {"github_repo": "o/a"},
        "pkg-b": {"github_repo": "o/b"},
        "pkg-c": {"github_repo": "o/c"},
    }
    only = rotate_all(
        source_path=src,
        only=["pkg-a"],
        dry_run=True,
        ecosystem=eco,
        local_path_lookup=_NO_LOCAL,
    )
    excluded = rotate_all(
        source_path=src,
        exclude=["pkg-b"],
        dry_run=True,
        ecosystem=eco,
        local_path_lookup=_NO_LOCAL,
    )
    assert [r.package for r in excluded] == ["pkg-a", "pkg-c"]


def test_rotate_all_gh_missing_raises(tmp_path):
    """With an empty PATH (no `gh`), rotate_all must raise."""
    # Arrange
    # Act
    # Assert
    src = _write(tmp_path, _GOOD_PAYLOAD)
    saved = os.environ.get("PATH")
    os.environ["PATH"] = ""
    try:
        with pytest.raises(RuntimeError):
            rotate_all(source_path=src)
    finally:
        if saved is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = saved
