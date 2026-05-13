"""Unit tests for scitex_dev._creds._rotate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_dev._creds import _rotate
from scitex_dev._creds._rotate import (
    rotate_all,
    validate_source,
)

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


def test_validate_source_returns_state_on_good_file(tmp_path):
    p = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(p)
    assert state is not None
    assert state.sha256
    assert state.byte_count == len(p.read_text().encode("utf-8"))


def test_validate_source_missing_file_silent(tmp_path):
    assert validate_source(tmp_path / "no.json") is None


def test_validate_source_parse_error_raises(tmp_path):
    p = _write(tmp_path, "{not json")
    with pytest.raises(ValueError):
        validate_source(p)


def test_validate_source_missing_oauth_key_raises(tmp_path):
    p = _write(tmp_path, {"foo": "bar"})
    with pytest.raises(ValueError):
        validate_source(p)


def test_validate_source_expired_silent_ms(tmp_path):
    p = _write(tmp_path, {"claudeAiOauth": {"expiresAt": 1_000}})
    assert validate_source(p, now_ms=lambda: 2_000_000_000_000) is None


def test_validate_source_expired_silent_seconds(tmp_path):
    p = _write(tmp_path, {"claudeAiOauth": {"expires_at": 100}})
    assert validate_source(p, now_ms=lambda: 2_000_000_000_000) is None


# -------- rotate_all (mocked subprocess) --------------------------------


class _Run:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _patch_gh(monkeypatch, *, remote_sha=None, set_secret_ok=True, set_var_ok=True):
    """Patch the four gh-touching helpers + which()."""
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: "/usr/bin/gh")
    calls = {"secret": 0, "var_get": 0, "var_set": 0}

    def fake_run(argv, **kwargs):
        if argv[:3] == ["gh", "variable", "get"]:
            calls["var_get"] += 1
            if remote_sha is None:
                return _Run(returncode=1, stderr="not found")
            return _Run(returncode=0, stdout=remote_sha + "\n")
        if argv[:3] == ["gh", "secret", "set"]:
            calls["secret"] += 1
            return _Run(
                returncode=0 if set_secret_ok else 1,
                stderr="" if set_secret_ok else "boom",
            )
        if argv[:3] == ["gh", "variable", "set"]:
            calls["var_set"] += 1
            return _Run(
                returncode=0 if set_var_ok else 1, stderr="" if set_var_ok else "boom"
            )
        if argv[:2] == ["git", "-C"] or argv[:1] == ["git"]:
            # _detect_repo_for_package falls back to registry on failure.
            return _Run(returncode=1, stdout="")
        return _Run(returncode=0)

    monkeypatch.setattr(_rotate.subprocess, "run", fake_run)
    # Also stub out check_output (used by _detect_repo_for_package).
    monkeypatch.setattr(
        _rotate.subprocess,
        "check_output",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()),
    )
    return calls


def _only_first_pkg(monkeypatch):
    """Pin ECOSYSTEM to a single deterministic package for tests."""
    monkeypatch.setattr(
        _rotate,
        "ECOSYSTEM",
        {"scitex-io": {"github_repo": "ywatanabe1989/scitex-io"}},
    )
    monkeypatch.setattr(_rotate, "get_local_path", lambda _: None)


def test_rotate_all_sha_match_skips_gh(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    _only_first_pkg(monkeypatch)
    calls = _patch_gh(monkeypatch, remote_sha=state.sha256)

    results = rotate_all(source_path=src, dry_run=False)
    assert len(results) == 1
    assert results[0].status == "unchanged"
    assert calls["secret"] == 0
    assert calls["var_set"] == 0


def test_rotate_all_sha_mismatch_rotates(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    _only_first_pkg(monkeypatch)
    calls = _patch_gh(monkeypatch, remote_sha="deadbeef")

    results = rotate_all(source_path=src, dry_run=False)
    assert results[0].status == "rotated"
    assert calls["secret"] == 1
    assert calls["var_set"] == 1


def test_rotate_all_missing_remote_skipped(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    # Registry entry has no github_repo and no local clone.
    monkeypatch.setattr(_rotate, "ECOSYSTEM", {"phantom-pkg": {}})
    monkeypatch.setattr(_rotate, "get_local_path", lambda _: None)
    _patch_gh(monkeypatch)

    results = rotate_all(source_path=src, dry_run=False)
    assert results[0].status == "skipped"
    assert "no remote" in results[0].message


def test_rotate_all_json_parse_error_raises(monkeypatch, tmp_path):
    src = _write(tmp_path, "{nope")
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: "/usr/bin/gh")
    with pytest.raises(ValueError):
        rotate_all(source_path=src)


def test_rotate_all_missing_oauth_raises(monkeypatch, tmp_path):
    src = _write(tmp_path, {"foo": "bar"})
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: "/usr/bin/gh")
    with pytest.raises(ValueError):
        rotate_all(source_path=src)


def test_rotate_all_expired_token_silent(monkeypatch, tmp_path):
    src = _write(tmp_path, {"claudeAiOauth": {"expiresAt": 1}})
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: "/usr/bin/gh")
    # Should return empty list — no per-repo activity.
    assert rotate_all(source_path=src) == []


def test_rotate_all_dry_run_makes_no_gh_set(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    _only_first_pkg(monkeypatch)
    calls = _patch_gh(monkeypatch, remote_sha="deadbeef")

    results = rotate_all(source_path=src, dry_run=True)
    assert results[0].status == "dry-run"
    assert calls["secret"] == 0
    assert calls["var_set"] == 0


def test_rotate_all_force_overrides_match(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    state = validate_source(src)
    _only_first_pkg(monkeypatch)
    calls = _patch_gh(monkeypatch, remote_sha=state.sha256)

    results = rotate_all(source_path=src, dry_run=False, force=True)
    assert results[0].status == "rotated"
    assert calls["secret"] == 1


def test_rotate_all_only_and_exclude_filters(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    monkeypatch.setattr(
        _rotate,
        "ECOSYSTEM",
        {
            "pkg-a": {"github_repo": "o/a"},
            "pkg-b": {"github_repo": "o/b"},
            "pkg-c": {"github_repo": "o/c"},
        },
    )
    monkeypatch.setattr(_rotate, "get_local_path", lambda _: None)
    _patch_gh(monkeypatch, remote_sha="x")

    only = rotate_all(source_path=src, only=["pkg-a"], dry_run=True)
    assert [r.package for r in only] == ["pkg-a"]
    excluded = rotate_all(source_path=src, exclude=["pkg-b"], dry_run=True)
    assert [r.package for r in excluded] == ["pkg-a", "pkg-c"]


def test_rotate_all_gh_missing_raises(monkeypatch, tmp_path):
    src = _write(tmp_path, _GOOD_PAYLOAD)
    monkeypatch.setattr(_rotate.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError):
        rotate_all(source_path=src)
