"""Tests for the resolved-checkout banner (anti wrong-tree footgun).

`audit-project` must surface the ABSOLUTE resolved path + git branch +
short HEAD sha of the tree it is about to grade BEFORE any results, so an
agent can never silently trust a green audit that ran against a stale
editable install or a sibling checkout resolved by name.

Two rails:
  * human — a scitex-logging INFO line ("<dist>: auditing <path> ...")
    emitted before results.
  * `--json` — `resolved_path` / `branch` / `head` fields in the payload.

PA-306 no-mocks: real `audit_project` runs against a real on-disk repo;
the git-positive test drives a real `git init` (not a mock). PA-307
test-quality: `# Arrange` / `# Act` / `# Assert` markers, one assertion
each.
"""

from __future__ import annotations

import contextlib
import io
import json as _json
import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project import audit_project
from scitex_dev._cli.audit._project._resolved_tree import resolved_context


def _make_repo(tmp_path: Path, name: str = "demo") -> Path:
    """Build a minimal SciTeX-shaped repo with one forbidden dir (PS-102)."""
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\nversion = "0.1.0"\n'
    )
    import_name = name.replace("-", "_")
    (tmp_path / "src" / import_name).mkdir(parents=True)
    (tmp_path / "src" / import_name / "__init__.py").write_text("")
    (tmp_path / "tests" / import_name).mkdir(parents=True)
    (tmp_path / "mgmt").mkdir()  # forbidden top-level dir → guarantees output
    return tmp_path


def _json_payload(repo: Path, name: str = "demo") -> dict:
    """Run audit_project in --json mode and return the parsed payload."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit_project(name, repo=repo, json_out=True)
    return _json.loads(buf.getvalue())


def _human_output(repo: Path, name: str = "demo") -> str:
    """Run audit_project in human mode; return combined stdout + banner text.

    The INFO banner is emitted through ``scitex_logging.getLogger(
    "scitex_dev.audit")`` (see ``.._emit.emit``), whose handler is bound to
    the REAL ``sys.stderr`` at import time — so ``redirect_stderr`` captures
    nothing whenever another test imported scitex-logging first (an
    xdist-order flake). We instead attach our OWN handler to that exact
    ``scitex_dev.audit`` logger, so the banner record lands in ``banner``
    deterministically regardless of the global handler state. ``stdout`` and
    real ``stderr`` are still captured so the fallback (no-scitex-logging)
    ``click.echo`` rail is covered too.
    """
    out = io.StringIO()
    err = io.StringIO()
    banner = io.StringIO()
    handler = logging.StreamHandler(banner)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.setLevel(logging.DEBUG)
    logger = logging.getLogger("scitex_dev.audit")
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            audit_project(name, repo=repo, json_out=False)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
    return out.getvalue() + err.getvalue() + banner.getvalue()


# ---------------------------------------------------------------------------
# resolved_context — pure resolution helper (fail-safe)
# ---------------------------------------------------------------------------


def test_resolved_context_none_repo_returns_all_none():
    """A repo that could not be located → every field None (no crash)."""
    # Arrange
    # Act
    ctx = resolved_context(None)
    # Assert
    assert ctx == {"resolved_path": None, "branch": None, "head": None}


def test_resolved_context_non_git_dir_still_gives_absolute_path(tmp_path):
    """A non-git tree still surfaces its absolute path (fail-safe)."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    ctx = resolved_context(repo)
    # Assert
    assert ctx["resolved_path"] == str(repo)


def test_resolved_context_non_git_dir_branch_is_none(tmp_path):
    """No git → branch resolves to None, never raising."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    ctx = resolved_context(repo)
    # Assert
    assert ctx["branch"] is None


@pytest.fixture
def git_repo(tmp_path) -> Path:
    """A real git checkout on branch `my-feature` with one commit."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = _make_repo(tmp_path)
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "checkout", "-q", "-b", "my-feature"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "-m", "init"],
        check=True,
    )
    return repo


def test_resolved_context_git_checkout_reports_branch(git_repo):
    """A real git checkout surfaces its branch name."""
    # Arrange
    # Act
    ctx = resolved_context(git_repo)
    # Assert
    assert ctx["branch"] == "my-feature"


def test_resolved_context_git_checkout_reports_head_sha(git_repo):
    """A real git checkout surfaces a short HEAD sha (>= 4 chars)."""
    # Arrange
    # Act
    head = resolved_context(git_repo)["head"]
    # Assert
    assert head is not None and len(head) >= 4


# ---------------------------------------------------------------------------
# --json rail: resolved_path / branch / head fields present in the payload
# ---------------------------------------------------------------------------


def test_json_payload_has_resolved_path_field(tmp_path):
    """--json output carries a `resolved_path` field."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    payload = _json_payload(repo)
    # Assert
    assert payload["resolved_path"] == str(repo)


def test_json_payload_has_branch_field(tmp_path):
    """--json output carries a `branch` key (present even when None)."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    payload = _json_payload(repo)
    # Assert
    assert "branch" in payload


def test_json_payload_has_head_field(tmp_path):
    """--json output carries a `head` key (present even when None)."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    payload = _json_payload(repo)
    # Assert
    assert "head" in payload


def test_json_none_repo_payload_has_resolved_path_key():
    """The 'cannot locate' payload still carries a `resolved_path` key."""
    # Arrange — a distribution with no checkout anywhere.
    buf = io.StringIO()
    # Act
    with contextlib.redirect_stdout(buf):
        audit_project("nonexistent-pkg-zzz", repo=None, json_out=True)
    payload = _json.loads(buf.getvalue())
    # Assert
    assert payload["resolved_path"] is None


# ---------------------------------------------------------------------------
# human rail: the banner surfaces the resolved path BEFORE results
# ---------------------------------------------------------------------------


def test_human_output_surfaces_resolved_path(tmp_path):
    """The human banner names the absolute tree being audited."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    text = _human_output(repo)
    # Assert
    assert str(repo) in text


def test_human_output_banner_says_auditing(tmp_path):
    """The banner uses the 'auditing <path>' phrasing before results."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    text = _human_output(repo)
    # Assert
    assert f"auditing {repo}" in text


# ---------------------------------------------------------------------------
# resolution-rule token: the banner/payload name WHICH rule picked the tree
# (operator directive 2026-07-21 — wrong-tree resolutions must be
# diagnosable at a glance: explicit / cwd / registry / import / proj-guess)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _chdir(target: Path):
    """`os.chdir` to `target`, restoring the previous CWD on exit."""
    import os

    previous = Path.cwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(previous)


def test_human_banner_names_the_explicit_resolution_rule(tmp_path):
    """An explicitly passed repo is announced as resolved 'via explicit'."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    text = _human_output(repo)
    # Assert
    assert "via explicit" in text


def test_json_payload_reports_resolved_via_explicit(tmp_path):
    """--json carries `resolved_via` = 'explicit' for a passed repo."""
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    payload = _json_payload(repo)
    # Assert
    assert payload["resolved_via"] == "explicit"


def test_json_payload_reports_resolved_via_cwd_inside_checkout(git_repo):
    """No repo + cwd inside the checkout → `resolved_via` = 'cwd'."""
    # Arrange — cwd inside a real git checkout whose pyproject names `demo`.
    buf = io.StringIO()
    # Act
    with _chdir(git_repo), contextlib.redirect_stdout(buf):
        audit_project("demo", repo=None, json_out=True)
    payload = _json.loads(buf.getvalue())
    # Assert
    assert payload["resolved_via"] == "cwd"


def test_caller_supplied_resolved_via_overrides_the_inferred_label(tmp_path):
    """The CLI's registry rule survives into the payload via `resolved_via`."""
    # Arrange — simulate `ecosystem audit-project` resolving via the registry.
    repo = _make_repo(tmp_path)
    buf = io.StringIO()
    # Act
    with contextlib.redirect_stdout(buf):
        audit_project("demo", repo=repo, json_out=True, resolved_via="registry")
    payload = _json.loads(buf.getvalue())
    # Assert
    assert payload["resolved_via"] == "registry"
