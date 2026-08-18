#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Staleness self-check decision logic against REAL fixtures (no mocks, PA-306).

The boot-path check fires on every command that loads scitex-dev (e.g.
`sac --version`). It warns ONLY when a NEWER scitex-dev is AVAILABLE — the
installed one is genuinely BEHIND:

  * editable install → HEAD behind `origin/<branch>` → `git -C <abs> pull
    --ff-only` (CWD-independent, non-destructive; NEVER bare / `--rebase`).
  * wheel install → installed version < a pre-existing cached latest →
    `pip install -U scitex-dev`.

Being AHEAD of the last release tag (unreleased dev commits) is NOT stale and
is NEVER flagged — that ahead-of-tag false positive (which also emitted a bare
`git pull --rebase` bomb) is the reported bug. Severity is knob-controlled
(default `warn`; `error` hard-fails). Real git repos, real cache/knob files.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import subprocess
from pathlib import Path

from scitex_dev._release.check_editable_drift import (
    EXIT_STALE,
    _compute_drift,
    _git_state_key,
    _pypi_drift,
    _react_to_drift,
    _resolve_severity,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _head(repo: Path) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "f.txt").write_text("v1")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "c1")
    _git(repo, "branch", "-M", "develop")
    return repo


def _set_upstream(repo: Path, sha: str) -> None:
    """Point develop's upstream at origin/develop pinned to `sha` (offline)."""
    _git(repo, "remote", "add", "origin", str(repo))
    _git(repo, "update-ref", "refs/remotes/origin/develop", sha)
    _git(repo, "branch", "--set-upstream-to=origin/develop", "develop")


@contextlib.contextmanager
def _environ(**overrides: str | None):
    saved = {k: os.environ.get(k) for k in overrides}
    try:
        for key, value in overrides.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --- Editable: the reported bug — ahead of tag, level with remote ------------


def test_ahead_of_tag_level_with_remote_no_warning(tmp_path):
    # Arrange — tag v0.32.0, +8 commits, upstream pinned AT HEAD (develop is
    # legitimately ahead of the tag but level with origin/develop).
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.32.0")
    for i in range(8):
        (repo / "f.txt").write_text(f"c{i}")
        _git(repo, "commit", "-aqm", f"c{i}")
    _set_upstream(repo, _head(repo))
    # Act
    result = _compute_drift(repo)
    # Assert — ahead-of-tag is NOT stale.
    assert result is None


# --- The cache key: it must observe a fast-forward ---------------------------
#
# REGRESSION. The key used to be a composite MTIME of
# max(.git/HEAD, packed-refs, refs/tags/). A fast-forward pull advances
# refs/heads/<branch> and never touches .git/HEAD — a symref whose CONTENT
# does not change when the branch moves — so the cache did not invalidate on
# the single commonest event this check exists to detect. The warning then
# survived its own prescribed remedy, naming a commit already an ancestor of
# HEAD, which is indistinguishable from a warning that is stuck on.


def _behind_repo_with_upstream(tmp_path: Path) -> Path:
    """A develop that is two commits behind its pinned origin/develop."""
    repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    (repo / "f.txt").write_text("v3")
    _git(repo, "commit", "-aqm", "c3")
    ahead_sha = _head(repo)
    _git(repo, "checkout", "-q", "-B", "develop", "HEAD~2")
    _set_upstream(repo, ahead_sha)
    return repo


def test_state_key_changes_when_the_branch_fast_forwards(tmp_path):
    """The regression: the old mtime key returned the SAME value here."""
    # Arrange
    repo = _behind_repo_with_upstream(tmp_path)
    before = _git_state_key(repo)
    # Act — fast-forward develop onto its upstream, as `pull --ff-only` does.
    _git(repo, "merge", "-q", "--ff-only", "origin/develop")
    # Assert
    assert _git_state_key(repo) != before


def test_head_file_is_untouched_by_a_fast_forward(tmp_path):
    """Why the mtime key failed — the control, not a restatement.

    Pins the mechanism rather than the symptom: if this ever stops holding,
    the regression above would pass for a reason unrelated to the fix.
    """
    # Arrange
    repo = _behind_repo_with_upstream(tmp_path)
    before = (repo / ".git" / "HEAD").read_bytes()
    # Act
    _git(repo, "merge", "-q", "--ff-only", "origin/develop")
    # Assert — HEAD is a symref; its content does not move with the branch.
    assert (repo / ".git" / "HEAD").read_bytes() == before


def test_state_key_is_none_outside_a_repo(tmp_path):
    # Arrange
    plain = tmp_path / "plain"
    plain.mkdir()
    # Act
    result = _git_state_key(plain)
    # Assert
    assert result is None


def test_fast_forwarded_checkout_reports_no_drift(tmp_path):
    """End to end: after the remedy, the warning must be gone."""
    # Arrange
    repo = _behind_repo_with_upstream(tmp_path)
    _git(repo, "merge", "-q", "--ff-only", "origin/develop")
    # Act
    result = _compute_drift(repo)
    # Assert
    assert result is None


# --- Editable: behind the remote --------------------------------------------


def test_behind_remote_remedy_is_cwd_safe_ff_only(tmp_path):
    # Arrange — upstream is 2 commits ahead of HEAD.
    repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    (repo / "f.txt").write_text("v3")
    _git(repo, "commit", "-aqm", "c3")
    ahead_sha = _head(repo)
    _git(repo, "checkout", "-q", "-B", "develop", "HEAD~2")
    _set_upstream(repo, ahead_sha)
    # Act
    result = _compute_drift(repo)
    # Assert — remedy carries the RESOLVED absolute path, ff-only.
    assert f"git -C {repo} pull --ff-only" in result


def test_behind_remote_never_bare_git_pull(tmp_path):
    # Arrange — same behind-remote shape.
    repo = _init_repo(tmp_path)
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    ahead_sha = _head(repo)
    _git(repo, "checkout", "-q", "-B", "develop", "HEAD~1")
    _set_upstream(repo, ahead_sha)
    # Act
    result = _compute_drift(repo)
    # Assert — the bare/destructive form is never emitted.
    assert "git pull" not in result


# --- Editable: fail-safe -----------------------------------------------------


def test_not_a_repo_is_none(tmp_path):
    # Arrange
    plain = tmp_path / "plain"
    plain.mkdir()
    # Act
    result = _compute_drift(plain)
    # Assert — no exception, no warning.
    assert result is None


def test_no_upstream_is_none(tmp_path):
    # Arrange — commits and a tag, but no configured upstream / remote ref.
    repo = _init_repo(tmp_path)
    _git(repo, "tag", "v0.32.0")
    (repo / "f.txt").write_text("v2")
    _git(repo, "commit", "-aqm", "c2")
    # Act
    result = _compute_drift(repo)
    # Assert — unresolved upstream ⇒ silent.
    assert result is None


# --- Wheel (PyPI) path -------------------------------------------------------


def test_pypi_behind_cached_latest_warns_pip_install_u(tmp_path):
    # Arrange — a version-cache file advertising a far-newer latest.
    cache = tmp_path / "version-latest.json"
    cache.write_text(json.dumps({"latest": "99.0.0"}))
    # Act
    with _environ(SCITEX_DEV_VERSION_CACHE=str(cache)):
        result = _pypi_drift("scitex-dev")
    # Assert
    assert "pip install -U scitex-dev" in result


def test_pypi_current_no_warning(tmp_path):
    # Arrange — cached latest is older than any installed version.
    cache = tmp_path / "version-latest.json"
    cache.write_text(json.dumps({"latest": "0.0.0"}))
    # Act
    with _environ(SCITEX_DEV_VERSION_CACHE=str(cache)):
        result = _pypi_drift("scitex-dev")
    # Assert
    assert result is None


def test_pypi_no_cache_is_silent(tmp_path):
    # Arrange — no cache file exists ⇒ no evidence, no network.
    missing = str(tmp_path / "absent.json")
    # Act
    with _environ(SCITEX_DEV_VERSION_CACHE=missing):
        result = _pypi_drift("scitex-dev")
    # Assert
    assert result is None


# --- Severity knob -----------------------------------------------------------


def test_default_severity_is_warn(tmp_path):
    # Arrange — point both knob layers at absent files (isolate from host).
    missing_cfg = str(tmp_path / "nope.yaml")
    missing_knob = str(tmp_path / "nope.json")
    # Act
    with _environ(SCITEX_DEV_CONFIG=missing_cfg, SCITEX_DEV_KNOB_STATE=missing_knob):
        severity = _resolve_severity()
    # Assert
    assert severity == "warn"


def test_knob_state_error_resolves_to_error(tmp_path):
    # Arrange — machine-managed knob-state escalates to error.
    knob = tmp_path / "knob-state.json"
    knob.write_text(json.dumps({"staleness_severity": "error"}))
    # Act
    with _environ(
        SCITEX_DEV_CONFIG=str(tmp_path / "absent.yaml"),
        SCITEX_DEV_KNOB_STATE=str(knob),
    ):
        severity = _resolve_severity()
    # Assert
    assert severity == "error"


def test_knob_state_overrides_config_yaml(tmp_path):
    # Arrange — config says warn, knob-state says error (knob-state wins).
    cfg = tmp_path / "config.yaml"
    cfg.write_text("staleness_severity: warn\n")
    knob = tmp_path / "knob-state.json"
    knob.write_text(json.dumps({"staleness_severity": "error"}))
    # Act
    with _environ(SCITEX_DEV_CONFIG=str(cfg), SCITEX_DEV_KNOB_STATE=str(knob)):
        severity = _resolve_severity()
    # Assert
    assert severity == "error"


def test_error_severity_returns_stale_exit_code():
    # Arrange
    msg = "editable scitex-dev: HEAD (abc) is 2 commit(s) behind its remote."
    # Act — capture stderr so the emit does not pollute test output.
    with contextlib.redirect_stderr(io.StringIO()):
        code = _react_to_drift(msg, "error")
    # Assert — hard-fail (non-zero) after printing.
    assert code == EXIT_STALE


def test_warn_severity_returns_zero():
    # Arrange
    msg = "editable scitex-dev: HEAD (abc) is 2 commit(s) behind its remote."
    # Act
    with contextlib.redirect_stderr(io.StringIO()):
        code = _react_to_drift(msg, "warn")
    # Assert — continue (exit 0).
    assert code == 0


@contextlib.contextmanager
def _capture_drift_log(buf: io.StringIO):
    """Deterministically capture the staleness line into ``buf``.

    ``_log_stale`` emits through ``scitex_logging.getLogger("scitex_dev")``,
    whose StreamHandler is bound to the REAL ``sys.stderr`` at import time —
    so ``contextlib.redirect_stderr`` (which swaps ``sys.stderr`` afterwards)
    captures nothing whenever another test imported scitex-logging first, an
    xdist-order flake. We instead attach our OWN handler to that exact
    ``scitex_dev`` logger, so the record lands in ``buf`` regardless of the
    global handler state; the ``levelname`` carries the WARN/ERRO prefix the
    assertion looks for. The buffer is also passed as the plain fallback
    ``stream`` so the no-scitex-logging path lands in ``buf`` too.
    """
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("scitex_dev")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


def test_warn_output_carries_severity_prefix():
    # Arrange — the message goes through scitex-logging, which auto-prefixes.
    msg = "editable scitex-dev: HEAD (abc) is 2 commit(s) behind its remote."
    buf = io.StringIO()
    # Act — capture on the scitex_dev logger (xdist-deterministic; NOT
    # redirect_stderr, which scitex-logging's import-time binding defeats).
    with _capture_drift_log(buf):
        _react_to_drift(msg, "warn", stream=buf)
    # Assert
    assert "WARN" in buf.getvalue()


def test_error_output_carries_severity_prefix():
    # Arrange
    msg = "editable scitex-dev: HEAD (abc) is 2 commit(s) behind its remote."
    buf = io.StringIO()
    # Act
    with _capture_drift_log(buf):
        _react_to_drift(msg, "error", stream=buf)
    # Assert — scitex-logging emits "ERRO:"; the fallback emits "ERROR:".
    assert "ERRO" in buf.getvalue().upper()


# EOF
