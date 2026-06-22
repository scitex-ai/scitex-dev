"""Unit tests for ``scitex-dev ci runner ensure --fleet`` — the fleet SOLVER.

Covers:
  * config opt-in (``fleet_enabled``) + ci-root resolution,
  * the on-node bash script the pass hands to ``reservations exec`` (it must
    discover ``actions-runner-*``, decide liveness by the runner's own argv,
    and relaunch dead-but-registered runners via the shipped launcher),
  * output parsing into ``FleetResult``,
  * one full pass driven by a real ``scitex-hpc`` CLI fake (no mocks of our own
    code — PA-306 / STX-NM*; the ``hpc_runner`` seam returns canned
    ``reservations exec`` output).

One assertion per test (STX-TQ007); AAA markers per STX-TQ002.
"""

from __future__ import annotations

import pytest

from scitex_dev.ci.runner import _fleet


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeComputeExec:
    """Compute-node exec fake — records the on-node script; returns one response.

    Mirrors production's seam: ``(script) -> CompletedProcess``. Recording the
    script lets tests assert what the node would run (glob, liveness predicate,
    DRY gate) without any ssh.
    """

    def __init__(self, response: _FakeCompletedProcess):
        self._response = response
        self.scripts: list[str] = []

    def __call__(self, script: str) -> _FakeCompletedProcess:
        self.scripts.append(script)
        return self._response


def _cfg(**reservation_overrides) -> dict:
    reservation = {
        "name": "ci-res",
        "cli": "scitex-hpc",
        "host": "spartan",
    }
    reservation.update(reservation_overrides)
    return {
        "hpc": {
            "ssh_host": "spartan",
            "user": "u",
            "apptainer": "/x/apptainer",
            "sif": "/x.sif",
        },
        "runner": {
            "name": "spartan-cpu-runner-01",
            "labels": ["self-hosted", "spartan-cpu"],
            "home": "/data/ci/actions-runner",
            "wrap_log": "/data/ci/runner-wrap.log",
        },
        "github": {"default_repo": "owner/repo", "pat_env": "FLEET_TEST_PAT"},
        "reservation": reservation,
    }


# ---------------------------------------------------------------------------
# fleet_enabled — the auto-trigger knob
# ---------------------------------------------------------------------------


def test_fleet_disabled_by_default():
    # Arrange — bare reservation, no fleet knob.
    cfg = _cfg()
    # Act / Assert
    assert _fleet.fleet_enabled(cfg) is False


def test_fleet_enabled_when_flag_true():
    # Arrange — operator flips reservation.fleet: true.
    cfg = _cfg(fleet=True)
    # Act / Assert
    assert _fleet.fleet_enabled(cfg) is True


def test_fleet_enabled_when_repos_listed():
    # Arrange — an explicit allow-list also opts in (forward-compat knob).
    cfg = _cfg(repos=["owner/a", "owner/b"])
    # Act / Assert
    assert _fleet.fleet_enabled(cfg) is True


# ---------------------------------------------------------------------------
# fleet_ci_root — where the actions-runner-* glob is rooted
# ---------------------------------------------------------------------------


def test_ci_root_is_parent_of_runner_home():
    # Arrange — per-repo homes are siblings of the config-managed home.
    cfg = _cfg()
    # Act
    root = _fleet.fleet_ci_root(cfg)
    # Assert
    assert root == "/data/ci"


def test_ci_root_explicit_override_wins():
    # Arrange — explicit fleet_root supersedes the derived parent.
    cfg = _cfg(fleet_root="/other/ci")
    # Act
    root = _fleet.fleet_ci_root(cfg)
    # Assert
    assert root == "/other/ci"


# ---------------------------------------------------------------------------
# build_fleet_script — the on-node command (pure)
# ---------------------------------------------------------------------------


def _script(dry_run: bool = False) -> str:
    return _fleet.build_fleet_script(
        ci_root="/data/ci",
        launcher_content="#!/bin/bash\necho launcher\n",
        gh_token="TKN",
        apptainer="/x/apptainer",
        sif="/x.sif",
        wrap_log_dir="/data/ci",
        dry_run=dry_run,
    )


def test_script_globs_actions_runner_dirs():
    # Arrange / Act
    script = _script()
    # Assert — discovery globs the per-repo homes (the -* suffix excludes the
    # no-suffix config-managed home).
    assert "/data/ci/actions-runner-*" in script


def test_script_checks_liveness_by_listener_argv():
    # Arrange / Act
    script = _script()
    # Assert — liveness uses the runner's OWN argv path, not a generic name.
    assert '"$d/bin/Runner.Listener"' in script


def test_script_embeds_launcher_content():
    # Arrange / Act
    script = _script()
    # Assert — the shipped launcher is re-staged inside the same exec.
    assert "echo launcher" in script


def test_script_restages_launcher_on_shared_fs():
    # Arrange / Act
    script = _script()
    # Assert — staged under the ci-root's run/ dir (shared FS, not /tmp).
    assert "/data/ci/run/scitex_ci_launcher.sh" in script


def test_script_detaches_with_setsid_nohup():
    # Arrange / Act
    script = _script()
    # Assert — same detach mechanism as the single-repo path.
    assert "setsid nohup bash" in script


def test_script_passes_token_via_env_not_argv():
    # Arrange / Act
    script = _script()
    # Assert — the token is referenced via env, never spliced into a runner argv.
    assert 'GH_TOKEN="$FLEET_GH_TOKEN"' in script


def test_script_dry_run_does_not_launch():
    # Arrange / Act — dry mode.
    script = _script(dry_run=True)
    # Assert — DRY gate set; the would-restart branch is taken instead of launch.
    assert "DRY=1" in script


def test_script_real_run_launches():
    # Arrange / Act — real mode.
    script = _script(dry_run=False)
    # Assert
    assert "DRY=0" in script


# ---------------------------------------------------------------------------
# parse_fleet_output — turn tagged lines into a FleetResult (pure)
# ---------------------------------------------------------------------------


def test_parse_collects_alive():
    # Arrange
    out = "FLEET_ALIVE\t/data/ci/actions-runner-tex\nFLEET_SUMMARY\talive=1\n"
    # Act
    res = _fleet.parse_fleet_output(out)
    # Assert
    assert res.alive == ["/data/ci/actions-runner-tex"]


def test_parse_collects_restarted():
    # Arrange
    out = "FLEET_RESTARTED\t/data/ci/actions-runner-io\n"
    # Act
    res = _fleet.parse_fleet_output(out)
    # Assert
    assert res.restarted == ["/data/ci/actions-runner-io"]


def test_parse_collects_would_restart():
    # Arrange
    out = "FLEET_WOULD_RESTART\t/data/ci/actions-runner-db\n"
    # Act
    res = _fleet.parse_fleet_output(out)
    # Assert
    assert res.would_restart == ["/data/ci/actions-runner-db"]


def test_parse_collects_failed():
    # Arrange — failed lines carry a reason in a 3rd column; only the dir matters.
    out = "FLEET_FAILED\t/data/ci/actions-runner-x\tno-.runner\n"
    # Act
    res = _fleet.parse_fleet_output(out)
    # Assert
    assert res.failed == ["/data/ci/actions-runner-x"]


def test_parse_total_counts_all_buckets():
    # Arrange
    out = (
        "FLEET_ALIVE\t/a\n"
        "FLEET_RESTARTED\t/b\n"
        "FLEET_WOULD_RESTART\t/c\n"
        "FLEET_FAILED\t/d\treason\n"
    )
    # Act
    res = _fleet.parse_fleet_output(out)
    # Assert
    assert res.total == 4


def test_parse_ignores_summary_and_blanks():
    # Arrange — the SUMMARY line and noise must not become fake entries.
    out = "FLEET_SUMMARY\talive=0\trestarted=0\n\nrandom banner line\n"
    # Act
    res = _fleet.parse_fleet_output(out)
    # Assert
    assert res.total == 0


# ---------------------------------------------------------------------------
# run_fleet_ensure — full pass with a real scitex-hpc fake (no mocks)
# ---------------------------------------------------------------------------


def test_run_fleet_runs_the_onnode_script(monkeypatch):
    # Arrange — token present; fake returns one alive runner. The pass must hand
    # the discover+restart script to the compute-node exec (one ssh to the node).
    monkeypatch.setenv("FLEET_TEST_PAT", "tkn")
    ex = _FakeComputeExec(
        _FakeCompletedProcess(stdout="FLEET_ALIVE\t/data/ci/actions-runner-tex\n")
    )
    cfg = _cfg()
    # Act
    _fleet.run_fleet_ensure(cfg, node="spartan-bm7", compute_exec=ex)
    # Assert — the on-node script globs the per-repo runner homes.
    assert "/data/ci/actions-runner-*" in ex.scripts[0]


def test_run_fleet_parses_alive_and_restarted(monkeypatch):
    # Arrange — one alive, one restarted.
    monkeypatch.setenv("FLEET_TEST_PAT", "tkn")
    out = (
        "FLEET_ALIVE\t/data/ci/actions-runner-tex\n"
        "FLEET_RESTARTED\t/data/ci/actions-runner-io\n"
        "FLEET_SUMMARY\talive=1\trestarted=1\n"
    )
    ex = _FakeComputeExec(_FakeCompletedProcess(stdout=out))
    cfg = _cfg()
    # Act
    res = _fleet.run_fleet_ensure(cfg, node="spartan-bm7", compute_exec=ex)
    # Assert
    assert (len(res.alive), len(res.restarted)) == (1, 1)


def test_run_fleet_dry_run_passes_dry_to_script(monkeypatch):
    # Arrange — dry pass must hand a DRY=1 script to the node exec.
    monkeypatch.setenv("FLEET_TEST_PAT", "tkn")
    ex = _FakeComputeExec(_FakeCompletedProcess(stdout="FLEET_SUMMARY\talive=0\n"))
    cfg = _cfg()
    # Act
    _fleet.run_fleet_ensure(cfg, node="spartan-bm7", dry_run=True, compute_exec=ex)
    # Assert — the script is the dry variant.
    assert "DRY=1" in ex.scripts[0]


def test_run_fleet_raises_on_exec_failure(monkeypatch):
    # Arrange — a non-zero on-node exec is a real error (fail-loud), not a no-op.
    monkeypatch.setenv("FLEET_TEST_PAT", "tkn")
    ex = _FakeComputeExec(_FakeCompletedProcess(returncode=255, stderr="ssh: timeout"))
    cfg = _cfg()
    # Act / Assert
    with pytest.raises(Exception, match="fleet pass"):
        _fleet.run_fleet_ensure(cfg, node="spartan-bm7", compute_exec=ex)


def test_run_fleet_requires_a_node(monkeypatch):
    # Arrange — no allocated node (freshly booked / PENDING) → cannot ssh.
    monkeypatch.setenv("FLEET_TEST_PAT", "tkn")
    cfg = _cfg()
    ex = _FakeComputeExec(_FakeCompletedProcess())
    # Act / Assert
    with pytest.raises(Exception, match="compute node"):
        _fleet.run_fleet_ensure(cfg, node="", compute_exec=ex)


# EOF
