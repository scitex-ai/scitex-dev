#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the three-layer config drift check.

The assertions that matter here are the NEGATIVE ones. This job exists because
a check can be exact and still measure the wrong thing, and because "could not
measure" reads as "fine" unless something forbids it. So the tests pin:

  * UNMEASURED is not a pass, at every level (finding, result, exit code)
  * a host that answers nothing is UNREACHABLE, not silently skipped
  * the three drift hops are told apart, since the verdict names the fix
"""

from __future__ import annotations

import io
import subprocess
from types import SimpleNamespace

from scitex_dev._ecosystem_jobs._config_drift import (
    DEPLOY_PENDING,
    IN_SYNC,
    LIVE_AHEAD,
    PULL_PENDING,
    UNMEASURED,
    UNREACHABLE,
    ConfigDriftFinding,
    run_once,
)


def _runner_returning(stdout: str, stderr: str = ""):
    """A fake ssh that replies with fixed remote output."""

    def _run(argv, **kwargs):  # noqa: ARG001
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=0)

    return _run


class TestVerdictsAreDistinguished:
    def test_in_sync_host_passes(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|IN_SYNC|abc1234 (copied)\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.ok is True

    def test_deploy_pending_is_reported_as_drift(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|DEPLOY_PENDING|stale copy\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert [f.verdict for f in result.drifted] == [DEPLOY_PENDING]

    def test_pull_pending_is_distinguished_from_deploy_pending(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|PULL_PENDING|4 commits behind\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.findings[0].verdict == PULL_PENDING

    def test_live_ahead_is_distinguished(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|LIVE_AHEAD|uncommitted edit\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.findings[0].verdict == LIVE_AHEAD


class TestUnmeasuredIsNeverAPass:
    """The blind spot must not render as success — that is the whole defect."""

    def test_unmeasured_finding_is_not_a_pass(self):
        # Arrange
        finding = ConfigDriftFinding("h1", "/p", UNMEASURED, "no repo")
        # Act
        is_pass = finding.is_pass
        # Assert
        assert is_pass is False

    def test_result_is_not_ok_when_anything_is_unmeasured(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|UNMEASURED|no repo at $HOME/.dotfiles\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.ok is False

    def test_unmeasured_exits_2_not_0(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|UNMEASURED|fetch failed\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.exit_code == 2

    def test_unmeasured_is_not_counted_as_drift_either(self):
        # Arrange
        runner = _runner_returning("/home/u/.claude/c.md|UNMEASURED|absent at ref\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.drifted == []

    def test_a_mix_of_in_sync_and_unmeasured_is_still_not_ok(self):
        # Arrange -- the dangerous shape: most hosts fine, one unknown
        runner = _runner_returning(
            "/p|IN_SYNC|abc1234 (symlinked)\n/q|UNMEASURED|deployed path does not exist\n"
        )
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.ok is False


class TestAHostThatSaysNothing:
    def test_empty_ssh_output_is_unreachable_not_skipped(self):
        # Arrange
        runner = _runner_returning("", stderr="ssh: connect: No route to host")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.findings[0].verdict == UNREACHABLE

    def test_unreachable_host_makes_the_run_not_ok(self):
        # Arrange
        runner = _runner_returning("")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert result.ok is False

    def test_a_raising_runner_becomes_a_verdict_not_a_crash(self):
        # Arrange
        def _boom(argv, **kwargs):  # noqa: ARG001
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=1)

        # Act
        result = run_once(hosts=("h1",), runner=_boom)
        # Assert
        assert result.findings[0].verdict == UNREACHABLE

    def test_no_hosts_at_all_is_not_a_pass(self):
        # Arrange
        runner = _runner_returning("/p|IN_SYNC|abc1234 (copied)\n")
        # Act
        result = run_once(hosts=(), runner=runner)
        # Assert
        assert result.ok is False


class TestReportNamesTheLayout:
    """A symlinked host matches by construction; the report must say so."""

    def test_in_sync_detail_carries_the_layout(self):
        # Arrange
        runner = _runner_returning("/p|IN_SYNC|abc1234 (symlinked)\n")
        # Act
        result = run_once(hosts=("h1",), runner=runner)
        # Assert
        assert "symlinked" in result.findings[0].detail

    def test_written_report_states_incomplete_for_unmeasured(self):
        # Arrange
        runner = _runner_returning("/p|UNMEASURED|no repo\n")
        buf = io.StringIO()
        # Act
        run_once(hosts=("h1",), runner=runner, out=buf)
        # Assert
        assert "NOT a pass" in buf.getvalue()


class TestTheRemoteScriptMeasuresTheDeployedPath:
    """Guards the defect that produced this job: the wrong left-hand side."""

    def test_pairs_are_passed_as_repo_relative_equals_deployed_path(self):
        # Arrange
        seen = {}

        def _capture(argv, **kwargs):
            seen["argv"] = argv
            return SimpleNamespace(stdout="/p|IN_SYNC|a (copied)\n", stderr="", returncode=0)

        # Act
        run_once(hosts=("h1",), pairs=(("repo/rel.md", "$HOME/live.md"),), runner=_capture)
        # Assert
        assert "repo/rel.md=$HOME/live.md" in " ".join(seen["argv"])

    def test_the_remote_body_hashes_the_deployed_file(self):
        # Arrange
        from scitex_dev._ecosystem_jobs._config_drift import _REMOTE

        # Act
        hashes_live = 'sha256sum "$live"' in _REMOTE
        # Assert
        assert hashes_live is True

    def test_the_remote_body_guards_the_empty_hash_on_both_sides(self):
        # Arrange
        from scitex_dev._ecosystem_jobs._config_drift import _REMOTE

        # Act
        guards = _REMOTE.count('= "$EMPTY_SHA"')
        # Assert
        assert guards == 2


# EOF
