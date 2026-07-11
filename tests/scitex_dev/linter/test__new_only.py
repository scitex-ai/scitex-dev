"""Tests for the NEW-ONLY baseline gate (``validate-files --new-only``).

Safety pair for the research-mode severity promotion (#264 / #265): under
``--new-only`` only NEWLY-introduced findings keep their promoted ``error``
severity (and block the post-edit hook), while PRE-EXISTING findings present
at the baseline ref are capped to ``warning`` (visible, non-blocking).

These tests use REAL temp git repos (``git init`` + commit a baseline, then
mutate the working tree) — NO mocks. The driving rule is ``STX-NL001`` (a
bare integer literal >= 1000), which is dependency-free (no scitex / figrecipe
plugin needed) and lives in category ``style``; the temp repo's
``pyproject.toml`` promotes it to ``error`` via ``per-rule-severity`` so the
test exercises the real promotion -> gate flow hermetically.
"""

from __future__ import annotations

import subprocess

import pytest

from scitex_dev.linter._cmd_check import _do_check
from scitex_dev.linter._new_only import (
    apply_new_only,
    baseline_source,
    finding_key,
)
from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig

# A line that trips STX-NL001 (bare 1234, no `_` separator, >= 1000).
_NL001_LINE = "x = 1234\n"
# A second, DISTINCT NL001 violation (different literal/content) — used as
# the "newly added" finding so it keys differently from the baseline one.
_NL001_LINE_NEW = "y = 5678\n"

# Promote NL001 to error so the gate has something to cap/keep. Mirrors the
# research-mode promotion without depending on a leaf plugin.
_PROMOTE_NL001 = LinterConfig(per_rule_severity={"STX-NL001": "error"})


def _git(repo, *args):
    """Run a git command in ``repo`` (real subprocess, check=True)."""
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_repo(tmp_path):
    """A real git repo with identity configured (no global config reliance)."""
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    return tmp_path


def _write_pyproject(repo):
    """Promote NL001 to error in the repo so validate-files emits it as error."""
    (repo / "pyproject.toml").write_text(
        "[tool.scitex-dev.linter]\n"
        'per-rule-severity = { "STX-NL001" = "error" }\n'
    )


def _sev_of(issues, rule_id):
    for i in issues:
        if i.rule.id == rule_id:
            return i.rule.severity
    return None


def _issue_of(issues, rule_id):
    """Return the first Issue with ``rule_id`` (issue order is severity-sorted,
    so we can't rely on positional indexing across line shifts)."""
    for i in issues:
        if i.rule.id == rule_id:
            return i
    raise AssertionError(f"{rule_id} not found in {[i.rule.id for i in issues]}")


# --------------------------------------------------------------------- #
# Unit: apply_new_only / finding_key                                     #
# --------------------------------------------------------------------- #


class TestApplyNewOnlyUnit:
    def test_preexisting_error_capped_to_warning(self):
        # Arrange — same finding in baseline and current, at error severity.
        current = lint_source(_NL001_LINE, "s.py", _PROMOTE_NL001)
        baseline = lint_source(_NL001_LINE, "s.py", _PROMOTE_NL001)
        # Act
        out = apply_new_only(current, baseline)
        # Assert — pre-existing error downgraded to warning (non-blocking).
        assert _sev_of(out, "STX-NL001") == "warning"

    def test_current_baseline_starts_at_error_before_capping(self):
        # Arrange — fixture sanity: the promoted rule really is error first.
        current = lint_source(_NL001_LINE, "s.py", _PROMOTE_NL001)
        # Act
        sev = _sev_of(current, "STX-NL001")
        # Assert
        assert sev == "error"

    def test_new_error_kept_at_full_severity(self):
        # Arrange — current has a NL001 the (empty) baseline lacks.
        current = lint_source(_NL001_LINE, "s.py", _PROMOTE_NL001)
        # Act — empty baseline => everything is new.
        out = apply_new_only(current, [])
        # Assert — new error stays error (blocks).
        assert _sev_of(out, "STX-NL001") == "error"

    def test_finding_key_ignores_line_number(self):
        # Arrange — same violating line at two different line positions.
        a = lint_source(_NL001_LINE, "s.py", _PROMOTE_NL001)
        b = lint_source("\n\n\n" + _NL001_LINE, "s.py", _PROMOTE_NL001)
        # Act — key the NL001 finding in each (issue order is severity-sorted).
        keys_equal = finding_key(_issue_of(a, "STX-NL001")) == finding_key(
            _issue_of(b, "STX-NL001")
        )
        # Assert — identity keys identically despite the line shift.
        assert keys_equal


# --------------------------------------------------------------------- #
# End-to-end: _do_check with real git baselines                          #
# --------------------------------------------------------------------- #


class TestCheckFilesNewOnly:
    def test_a_preexisting_violation_not_reported_as_error(self, git_repo):
        # Arrange — commit a file whose ONLY violation is pre-existing.
        _write_pyproject(git_repo)
        f = git_repo / "script.py"
        f.write_text(_NL001_LINE)
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-m", "baseline")
        # Act — --new-only at severity error: the pre-existing error is capped
        # to warning, so it's filtered out by the error floor.
        rc = _do_check(
            str(f),
            as_json=False,
            no_color=True,
            severity="error",
            category=None,
            new_only=True,
            baseline="HEAD",
        )
        # Assert — exit code does NOT signal error (0 = clean at error floor).
        assert rc == 0

    def test_b_newly_added_violation_reported_at_error(self, git_repo):
        # Arrange — baseline has ONE violation; working tree adds a SECOND.
        _write_pyproject(git_repo)
        f = git_repo / "script.py"
        f.write_text(_NL001_LINE)
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-m", "baseline")
        # Mutate the working tree: keep the old line, add a NEW NL001.
        f.write_text(_NL001_LINE + _NL001_LINE_NEW)
        # Act
        rc = _do_check(
            str(f),
            as_json=False,
            no_color=True,
            severity="error",
            category=None,
            new_only=True,
            baseline="HEAD",
        )
        # Assert — the NEW violation keeps error severity -> exit 2 (blocks).
        assert rc == 2

    def test_c_line_shift_keeps_preexisting_classification(self, git_repo):
        # Arrange — baseline has the violation; working tree inserts blank
        # lines ABOVE it (shifting its line number) but introduces NOTHING new.
        _write_pyproject(git_repo)
        f = git_repo / "script.py"
        f.write_text(_NL001_LINE)
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-m", "baseline")
        # Shift the violation down by 5 blank lines — content-based match must
        # still classify it as PRE-EXISTING (not new).
        f.write_text("\n\n\n\n\n" + _NL001_LINE)
        # Act
        rc = _do_check(
            str(f),
            as_json=False,
            no_color=True,
            severity="error",
            category=None,
            new_only=True,
            baseline="HEAD",
        )
        # Assert — still pre-existing -> capped to warning -> no error exit.
        assert rc == 0

    def test_d_untracked_file_all_violations_new(self, git_repo):
        # Arrange — a file that was NEVER committed (untracked => empty
        # baseline => every finding is new).
        _write_pyproject(git_repo)
        _git(git_repo, "commit", "--allow-empty", "-m", "empty baseline")
        f = git_repo / "fresh.py"
        f.write_text(_NL001_LINE)
        # (deliberately NOT added/committed)
        # Act
        rc = _do_check(
            str(f),
            as_json=False,
            no_color=True,
            severity="error",
            category=None,
            new_only=True,
            baseline="HEAD",
        )
        # Assert — treated as new -> error severity kept -> exit 2.
        assert rc == 2

    def test_e_without_new_only_preexisting_reports_at_full_severity(
        self, git_repo
    ):
        # Arrange — same pre-existing-only file as case (a).
        _write_pyproject(git_repo)
        f = git_repo / "script.py"
        f.write_text(_NL001_LINE)
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-m", "baseline")
        # Act — WITHOUT --new-only: unchanged behavior, full severity.
        rc = _do_check(
            str(f),
            as_json=False,
            no_color=True,
            severity="error",
            category=None,
            new_only=False,
        )
        # Assert — pre-existing error reported at full severity -> exit 2.
        assert rc == 2


# --------------------------------------------------------------------- #
# baseline_source: real git show round-trip                              #
# --------------------------------------------------------------------- #


class TestBaselineSource:
    def test_returns_committed_content(self, git_repo):
        # Arrange
        f = git_repo / "a.py"
        f.write_text("x = 1\n")
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-m", "c1")
        f.write_text("x = 2\n")  # working tree diverges
        # Act
        src = baseline_source(f, "HEAD")
        # Assert — baseline content, NOT the working-tree content.
        assert src == "x = 1\n"

    def test_untracked_file_returns_none(self, git_repo):
        # Arrange
        _git(git_repo, "commit", "--allow-empty", "-m", "c0")
        f = git_repo / "never.py"
        f.write_text("x = 1\n")
        # Act
        src = baseline_source(f, "HEAD")
        # Assert — untracked -> no baseline.
        assert src is None

    def test_outside_repo_returns_none(self, tmp_path):
        # Arrange — a path that is in no git repo at all.
        f = tmp_path / "loose.py"
        f.write_text("x = 1\n")
        # Act
        src = baseline_source(f, "HEAD")
        # Assert
        assert src is None


# EOF
