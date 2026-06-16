"""Regression tests for the 'ci runner up' wrapper builder (pure functions).

No mocks: _staging_paths / _build_wrapper_script are pure string builders, so
the tests just call them and assert on the result. They lock in the two bugs
that broke 'up' on Spartan:
  1. staging on /tmp (node-local on multi-login-node Spartan) -> shared FS;
  2. bare `srun` (not on the non-interactive PATH) -> absolute path.
"""

from __future__ import annotations

from scitex_dev.ci.runner._up import (
    _SRUN,
    _build_wrapper_script,
    _staging_paths,
)

_HOME = "/data/gpfs/projects/punim0264/ywatanabe/ci/actions-runner"


def _wrapper(**overrides) -> str:
    kwargs = dict(
        runner_home=_HOME,
        launcher_content="echo launcher",
        gh_token="ghp_xxx",
        gh_repo="ywatanabe1989/scitex-dev",
        runner_name="spartan-cpu-runner-01",
        runner_labels="self-hosted,spartan-cpu",
        apptainer="~/.env-3.11/bin/apptainer",
        sif="~/.scitex/dev/containers/ci-cpu.sif",
        wrap_log="/data/gpfs/projects/punim0264/ywatanabe/ci/runner-wrap.log",
        jobid="26030530",
    )
    kwargs.update(overrides)
    return _build_wrapper_script(**kwargs)


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


def test_wrapper_uses_absolute_srun_path() -> None:
    # Arrange
    # Act
    script = _wrapper()
    # Assert — bare `srun ` would fail on the non-interactive PATH.
    assert _SRUN in script


def test_wrapper_has_no_bare_srun_invocation() -> None:
    # Arrange
    # Act
    script = _wrapper()
    # Assert — the only `srun` token is the absolute one (no `nohup srun`).
    assert "nohup srun" not in script


def test_wrapper_writes_launcher_to_shared_stage_dir() -> None:
    # Arrange
    stage_dir, _wrap, launcher_remote = _staging_paths(_HOME)
    # Act
    script = _wrapper()
    # Assert — launcher heredoc targets the shared path, not /tmp.
    assert f"cat > '{launcher_remote}'" in script


def test_wrapper_overlaps_the_given_lease_jobid() -> None:
    # Arrange
    # Act
    script = _wrapper(jobid="99999")
    # Assert
    assert "--overlap --jobid=99999" in script
