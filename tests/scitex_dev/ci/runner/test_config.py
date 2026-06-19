"""Tests for the CI runner config loader (config.py).

No mocks, no monkeypatch: writes real YAML to tmp_path and passes it through
the loader's file-path seams (config_path / shared_path). Exercises the
config.yaml host reuse and fail-loud validation.
"""

from __future__ import annotations

import textwrap

import pytest

from scitex_dev.ci.runner import config


def _write(path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))


_SHARED = """
hosts:
  - name: spartan
    hostname: spartan.example.edu
    user: alice
  - name: nas
    hostname: nas.local
    user: bob
"""

_CI_RUNNER = """
hpc:
  host_ref: spartan
  apptainer: ~/.env/bin/apptainer
  sif: ~/ci.sif
runner:
  name: spartan-cpu-runner-01
  labels: [self-hosted, spartan-cpu]
  home: /punim/ci/actions-runner
  wrap_log: /punim/ci/wrap.log
ci_lease:
  jobname: spartan-ci-runner-permanent
  sbatch_script: ~/lease.sbatch
  renew_threshold_min: 1440
github:
  pat_env: SCITEX_DEV_GH_PAT
  default_repo: ywatanabe1989/scitex-dev
  variable_name: CI_RUNS_ON
watchdog:
  poll_interval_sec: 300
  offline_grace_min: 15
  alert_via: telegram
"""


def test_resolve_hpc_from_shared_reads_named_host(tmp_path) -> None:
    # Arrange
    shared = tmp_path / "config.yaml"
    _write(shared, _SHARED)
    # Act
    out = config._resolve_hpc_from_shared("spartan", shared_path=shared)
    # Assert
    assert out == {"user": "alice", "ssh_host": "spartan.example.edu"}


def test_resolve_hpc_from_shared_missing_file_returns_empty(tmp_path) -> None:
    # Arrange
    absent = tmp_path / "nope.yaml"
    # Act
    out = config._resolve_hpc_from_shared("spartan", shared_path=absent)
    # Assert
    assert out == {}


def test_load_runner_config_fills_user_from_shared(tmp_path) -> None:
    # Arrange
    shared = tmp_path / "config.yaml"
    _write(shared, _SHARED)
    runner_cfg = tmp_path / "config" / "ci-runner.yaml"
    _write(runner_cfg, _CI_RUNNER)
    # Act
    cfg = config.load_runner_config(config_path=runner_cfg, shared_path=shared)
    # Assert
    assert cfg["hpc"]["user"] == "alice"


def test_load_runner_config_fills_ssh_host_from_shared(tmp_path) -> None:
    # Arrange
    shared = tmp_path / "config.yaml"
    _write(shared, _SHARED)
    runner_cfg = tmp_path / "config" / "ci-runner.yaml"
    _write(runner_cfg, _CI_RUNNER)
    # Act
    cfg = config.load_runner_config(config_path=runner_cfg, shared_path=shared)
    # Assert
    assert cfg["hpc"]["ssh_host"] == "spartan.example.edu"


def test_explicit_host_overrides_shared(tmp_path) -> None:
    # Arrange
    shared = tmp_path / "config.yaml"
    _write(shared, _SHARED)
    runner_cfg = tmp_path / "config" / "ci-runner.yaml"
    _write(
        runner_cfg,
        _CI_RUNNER.replace(
            "host_ref: spartan", "host_ref: spartan\n  user: explicit_user"
        ),
    )
    # Act
    cfg = config.load_runner_config(config_path=runner_cfg, shared_path=shared)
    # Assert — explicit value wins (setdefault does not clobber it).
    assert cfg["hpc"]["user"] == "explicit_user"


def test_missing_required_key_raises_naming_the_path(tmp_path) -> None:
    # Arrange — explicit host (so hpc.* all present); drop runner.home so it is
    # the first missing required key the validator hits.
    shared = tmp_path / "nope.yaml"
    cfg_text = _CI_RUNNER.replace(
        "  host_ref: spartan",
        "  host_ref: spartan\n  user: alice\n  ssh_host: h",
    ).replace("  home: /punim/ci/actions-runner\n", "")
    runner_cfg = tmp_path / "config" / "ci-runner.yaml"
    _write(runner_cfg, cfg_text)
    # Act
    # Assert
    with pytest.raises(SystemExit, match="runner.home"):
        config.load_runner_config(config_path=runner_cfg, shared_path=shared)
