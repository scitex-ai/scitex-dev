"""Regression tests for the 'ci runner up' launch builders (pure functions).

No mocks: _staging_paths / _build_launcher_stage_script /
_build_compute_run_script / config.compute_ssh_cmd are pure string builders, so
the tests just call them and assert on the result.

They lock in the invariants of the SSH-vector fix (2026-06-17 admin incident,
~20 srun/login-node ceiling) AND the older staging fix:
  1. staging on /tmp (node-local on multi-login-node Spartan) -> shared FS;
  2. the launch leaves ZERO persistent login-node `srun` client per runner —
     the runner is started ON the compute node via ProxyJump with `setsid nohup`,
     and there is NO `srun` anywhere in the launch path.
"""

from __future__ import annotations

from scitex_dev.ci.runner import config
from scitex_dev.ci.runner._up import (
    _build_compute_run_script,
    _build_launcher_stage_script,
    _staging_paths,
)

_HOME = "/data/gpfs/projects/punim0264/ywatanabe/ci/actions-runner"
_TARGET = "ywatanabe@spartan.example.edu"
_NODE = "spartan-bm159"


def _stage(**overrides) -> str:
    kwargs = dict(
        runner_home=_HOME,
        launcher_content="echo launcher",
    )
    kwargs.update(overrides)
    return _build_launcher_stage_script(**kwargs)


def _run(**overrides) -> str:
    kwargs = dict(
        runner_home=_HOME,
        gh_token="ghp_xxx",
        gh_repo="ywatanabe1989/scitex-dev",
        runner_name="spartan-cpu-runner-01",
        runner_labels="self-hosted,spartan-cpu",
        apptainer="~/.env-3.11/bin/apptainer",
        sif="~/.scitex/dev/containers/ci-cpu.sif",
        wrap_log="/data/gpfs/projects/punim0264/ywatanabe/ci/runner-wrap.log",
    )
    kwargs.update(overrides)
    return _build_compute_run_script(**kwargs)


# -- staging paths ----------------------------------------------------------


def test_staging_dir_is_under_runner_home_parent() -> None:
    # Arrange
    # Act
    stage_dir, _wrap, _launch = _staging_paths(_HOME)
    # Assert
    assert stage_dir == "/data/gpfs/projects/punim0264/ywatanabe/ci/run"


def test_staging_dir_is_not_tmp() -> None:
    # Arrange
    # Act
    stage_dir, wrapper_remote, launcher_remote = _staging_paths(_HOME)
    # Assert — never node-local /tmp (the multi-login-node bug).
    assert not any(
        p.startswith("/tmp/") for p in (stage_dir, wrapper_remote, launcher_remote)
    )


# -- login-node staging script (file I/O only) ------------------------------


def test_stage_script_writes_launcher_to_shared_stage_dir() -> None:
    # Arrange
    _stage_dir, _wrap, launcher_remote = _staging_paths(_HOME)
    # Act
    script = _stage()
    # Assert — launcher heredoc targets the shared path, not /tmp.
    assert f"cat > '{launcher_remote}'" in script


def test_stage_script_starts_no_srun() -> None:
    # Arrange — the staging ssh must leave NOTHING running on the login node.
    # Act
    script = _stage()
    # Assert — no srun client is the whole point of the SSH-vector fix.
    assert "srun" not in script


def test_stage_script_starts_no_background_process() -> None:
    # Arrange
    # Act
    script = _stage()
    # Assert — pure file staging: no setsid/nohup/backgrounding on the login node.
    assert "setsid" not in script and "nohup" not in script


# -- compute-node run script (the detached launch) --------------------------


def test_run_script_detaches_launcher_without_srun() -> None:
    # Arrange — runs ON the compute node (reached via ProxyJump), so no srun.
    _stage_dir, _wrap, launcher_remote = _staging_paths(_HOME)
    # Act
    script = _run()
    # Assert — setsid+nohup bash launcher, and crucially NO srun anywhere.
    assert f"setsid nohup bash '{launcher_remote}'" in script


def test_run_script_invokes_no_srun_command() -> None:
    # Arrange — a login-node srun CLIENT is exactly what this fix removes; the
    # script must not INVOKE srun (a mention in a comment is fine, so check the
    # non-comment lines only).
    # Act
    script = _run()
    code_lines = [
        ln
        for ln in script.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    # Assert
    assert not any("srun" in ln for ln in code_lines)


def test_run_script_embeds_overridden_repo() -> None:
    # Arrange — ecosystem rollout: a runner for another repo on the shared lease.
    # Act
    script = _run(gh_repo="ywatanabe1989/scitex-todo")
    # Assert
    assert "export GH_REPO='ywatanabe1989/scitex-todo'" in script


def test_run_script_embeds_overridden_labels() -> None:
    # Arrange — extra label so a repo's legacy-labelled workflow still matches.
    # Act
    script = _run(runner_labels="self-hosted,spartan-cpu,scitex-ci")
    # Assert
    assert "export RUNNER_LABELS='self-hosted,spartan-cpu,scitex-ci'" in script


def test_run_script_exports_runner_home() -> None:
    # Arrange — down's per-runner kill matches on this exported RUNNER_HOME.
    # Act
    script = _run()
    # Assert
    assert f"export RUNNER_HOME='{_HOME}'" in script


# -- compute-node ssh command (ProxyJump) -----------------------------------


def test_compute_ssh_cmd_proxyjumps_through_login() -> None:
    # Arrange
    # Act
    cmd = config.compute_ssh_cmd(_TARGET, _NODE)
    # Assert — -J <login_target> places the jump host before the node hop.
    assert "-J" in cmd and cmd[cmd.index("-J") + 1] == _TARGET


def test_compute_ssh_cmd_reuses_user_on_inner_hop() -> None:
    # Arrange — same account on the compute node as the login target.
    # Act
    cmd = config.compute_ssh_cmd(_TARGET, _NODE)
    # Assert
    assert cmd[-1] == f"ywatanabe@{_NODE}"


def test_compute_ssh_cmd_accepts_new_host_key() -> None:
    # Arrange — compute nodes are ephemeral lease holders, not in known_hosts.
    # Act
    cmd = config.compute_ssh_cmd(_TARGET, _NODE)
    # Assert — accept-new (trust-on-first-use) so BatchMode does not hard-fail,
    # while a CHANGED key still fails loudly.
    assert "StrictHostKeyChecking=accept-new" in cmd


def test_compute_ssh_cmd_is_non_interactive() -> None:
    # Arrange — cron/agent context: no prompts allowed.
    # Act
    cmd = config.compute_ssh_cmd(_TARGET, _NODE)
    # Assert
    assert "BatchMode=yes" in cmd
