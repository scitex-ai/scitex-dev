#!/usr/bin/env python3
"""Tests for the host/scheduler-agnostic test-execution recipe.

Pins the recipe schema (default mode=local), YAML load, submit-template
rendering, the guard decision (remote-required + marker-env logic), and the
git-scope recipe discovery used by the pytest plugin. No mocks — recipes are
real tmp_path YAML files and env/cwd are passed in explicitly.
"""

from __future__ import annotations

from pathlib import Path

import os
import subprocess
import sys

from scitex_dev._core.test_execution import (
    ALLOCATED_CPUS_PY_SNIPPET,
    DEFAULT_MARKER_ENV,
    RECIPE_PATH_ENV,
    XDIST_AUTO_WORKERS_ENV,
    TestExecutionConfig,
    _pkg_short,
    allocated_cpus,
    discover_recipe,
    guard_message,
    is_on_sanctioned_remote,
    load_recipe,
    recipe_path,
    render_submit,
)


def test_malformed_yaml_recipe_fails_safe_to_local(tmp_path):
    # Arrange — a syntactically broken recipe the auto-loaded plugin must not choke on
    bad = tmp_path / "test-execution.yaml"
    bad.write_text(": : broken\n[unclosed")
    # Act
    recipe = load_recipe(bad)
    # Assert — fails safe to the inert default rather than raising
    assert recipe.mode == "local"


def test_invalid_mode_value_fails_safe_to_local(tmp_path):
    # Arrange — a recipe whose mode is not a known value
    bad = tmp_path / "test-execution.yaml"
    bad.write_text("mode: not-a-real-mode\n")
    # Act
    recipe = load_recipe(bad)
    # Assert — the __post_init__ ValueError is downgraded, never crashes pytest
    assert recipe.mode == "local"


def test_default_mode_is_local():
    # Arrange
    default_kwargs = {}
    # Act
    recipe = TestExecutionConfig(**default_kwargs)
    # Assert
    assert recipe.mode == "local"


def test_default_marker_env_name():
    # Arrange
    default_kwargs = {}
    # Act
    recipe = TestExecutionConfig(**default_kwargs)
    # Assert
    assert recipe.local_marker_env == DEFAULT_MARKER_ENV


def test_invalid_mode_raises_value_error():
    # Arrange
    raised = False
    # Act
    try:
        TestExecutionConfig(mode="bogus")
    except ValueError:
        raised = True
    # Assert
    assert raised is True


def test_load_recipe_absent_defaults_to_local(tmp_path):
    # Arrange
    missing = tmp_path / "nope.yaml"
    # Act
    recipe = load_recipe(missing)
    # Assert
    assert recipe.mode == "local"


def test_load_recipe_reads_remote_required(tmp_path):
    # Arrange
    p = tmp_path / "test-execution.yaml"
    p.write_text("mode: remote-required\nremote_host: cluster-01\n")
    # Act
    recipe = load_recipe(p)
    # Assert
    assert recipe.mode == "remote-required"


def test_load_recipe_reads_remote_host(tmp_path):
    # Arrange
    p = tmp_path / "test-execution.yaml"
    p.write_text("mode: remote-required\nremote_host: cluster-01\n")
    # Act
    recipe = load_recipe(p)
    # Assert
    assert recipe.remote_host == "cluster-01"


def test_load_recipe_collects_flat_params(tmp_path):
    # Arrange
    p = tmp_path / "test-execution.yaml"
    p.write_text("mode: remote-required\npartition: gpu-a100\n")
    # Act
    recipe = load_recipe(p)
    # Assert
    assert recipe.params["partition"] == "gpu-a100"


def test_load_recipe_collects_nested_params(tmp_path):
    # Arrange
    p = tmp_path / "test-execution.yaml"
    p.write_text("mode: local\nparams:\n  account: punim1234\n")
    # Act
    recipe = load_recipe(p)
    # Assert
    assert recipe.params["account"] == "punim1234"


def test_render_submit_fills_pytest_args():
    # Arrange
    recipe = TestExecutionConfig(
        mode="remote-required", submit_template="run {pytest_args}"
    )
    # Act
    rendered = render_submit(recipe, "-n auto tests/")
    # Assert
    assert rendered == "run -n auto tests/"


def test_render_submit_fills_host_token():
    # Arrange
    recipe = TestExecutionConfig(
        mode="remote-required",
        remote_host="cluster-01",
        submit_template="ssh {host} pytest {pytest_args}",
    )
    # Act
    rendered = render_submit(recipe, "tests/")
    # Assert
    assert "cluster-01" in rendered


def test_render_submit_fills_free_form_param():
    # Arrange
    recipe = TestExecutionConfig(
        mode="remote-required",
        submit_template="srun -p {partition} pytest {pytest_args}",
        params={"partition": "gpu-a100"},
    )
    # Act
    rendered = render_submit(recipe, "tests/")
    # Assert
    assert "-p gpu-a100" in rendered


def test_render_submit_leaves_unknown_placeholder_literal():
    # Arrange
    recipe = TestExecutionConfig(
        mode="remote-required", submit_template="run {unknown} {pytest_args}"
    )
    # Act
    rendered = render_submit(recipe, "tests/")
    # Assert
    assert "{unknown}" in rendered


def test_render_submit_without_template_raises():
    # Arrange
    recipe = TestExecutionConfig(mode="remote-required")
    raised = False
    # Act
    try:
        render_submit(recipe, "tests/")
    except ValueError:
        raised = True
    # Assert
    assert raised is True


def test_guard_message_none_for_local_mode():
    # Arrange
    recipe = TestExecutionConfig(mode="local")
    # Act
    message = guard_message(recipe, environ={})
    # Assert
    assert message is None


def test_guard_message_blocks_remote_required_without_marker():
    # Arrange
    recipe = TestExecutionConfig(mode="remote-required")
    # Act
    message = guard_message(recipe, environ={})
    # Assert
    assert message is not None


def test_guard_message_allows_when_marker_env_set():
    # Arrange
    recipe = TestExecutionConfig(mode="remote-required")
    # Act
    message = guard_message(recipe, environ={DEFAULT_MARKER_ENV: "1"})
    # Assert
    assert message is None


def test_guard_message_names_remote_host():
    # Arrange
    recipe = TestExecutionConfig(mode="remote-required", remote_host="cluster-01")
    # Act
    message = guard_message(recipe, environ={})
    # Assert
    assert "cluster-01" in message


def test_is_on_sanctioned_remote_true_when_marker_set():
    # Arrange
    recipe = TestExecutionConfig(mode="remote-required")
    # Act
    on_remote = is_on_sanctioned_remote(recipe, environ={DEFAULT_MARKER_ENV: "1"})
    # Assert
    assert on_remote is True


def test_pkg_short_strips_scitex_prefix():
    # Arrange
    pkg = "scitex-hpc"
    # Act
    short = _pkg_short(pkg)
    # Assert
    assert short == "hpc"


def test_recipe_path_explicit_wins():
    # Arrange
    explicit = "/tmp/custom-recipe.yaml"
    # Act
    resolved = recipe_path("scitex-io", path=explicit)
    # Assert
    assert resolved == Path("/tmp/custom-recipe.yaml")


def test_discover_recipe_env_path_wins(tmp_path):
    # Arrange
    p = tmp_path / "explicit.yaml"
    p.write_text("mode: remote-required\n")
    # Act
    recipe = discover_recipe(start=tmp_path, environ={RECIPE_PATH_ENV: str(p)})
    # Assert
    assert recipe.mode == "remote-required"


def test_discover_recipe_finds_project_scope(tmp_path):
    # Arrange
    (tmp_path / ".git").mkdir()
    scope = tmp_path / ".scitex" / "io"
    scope.mkdir(parents=True)
    (scope / "test-execution.yaml").write_text("mode: remote-required\n")
    # Act
    recipe = discover_recipe(start=tmp_path, environ={})
    # Assert
    assert recipe.mode == "remote-required"


def test_discover_recipe_defaults_local_without_git(tmp_path):
    # Arrange
    plain = tmp_path / "no-git"
    plain.mkdir()
    # Act
    recipe = discover_recipe(start=plain, environ={})
    # Assert
    assert recipe.mode == "local"


# ---------------------------------------------------------------------------
# allocated_cpus — the xdist worker-count policy (ADR-0004 P1(b)).
#
# These pin the behaviour that a bare `pytest -n auto` does NOT have: on the
# Spartan CI runner (48-CPU lease on a 128-CPU node) xdist asked psutil, got
# 128, and oversubscribed 2.7x. No mocks — env maps are passed in explicitly
# and the subprocess checks run the real snippet under a real interpreter.
# ---------------------------------------------------------------------------


def test_allocated_cpus_prefers_slurm_cpus_per_task():
    # Arrange — inside an srun/sbatch step the allocation is explicit
    env = {"SLURM_CPUS_PER_TASK": "48"}
    # Act
    n = allocated_cpus(environ=env)
    # Assert — the allocation, NOT the machine's core count
    assert n == 48


def test_allocated_cpus_falls_back_to_job_cpus_per_node():
    # Arrange — a batch allocation exposes only the per-node form
    env = {"SLURM_JOB_CPUS_PER_NODE": "48"}
    # Act
    n = allocated_cpus(environ=env)
    # Assert
    assert n == 48


def test_allocated_cpus_parses_repeated_node_count_form():
    # Arrange — Slurm writes "48(x2)" when several nodes share a count
    env = {"SLURM_JOB_CPUS_PER_NODE": "48(x2)"}
    # Act
    n = allocated_cpus(environ=env)
    # Assert — the leading integer is THIS node's count
    assert n == 48


def test_allocated_cpus_ignores_blank_and_non_numeric_slurm_vars():
    # Arrange — exactly what the CI runner exposes: the vars exist but empty
    env = {"SLURM_CPUS_PER_TASK": "", "SLURM_JOB_CPUS_PER_NODE": "  "}
    # Act
    n = allocated_cpus(environ=env)
    # Assert — falls through to affinity rather than crashing or returning 0
    assert n == len(os.sched_getaffinity(0))


def test_allocated_cpus_uses_affinity_when_no_slurm_env():
    # Arrange — a developer laptop: no allocation at all
    env: dict[str, str] = {}
    # Act
    n = allocated_cpus(environ=env)
    # Assert — the process's real affinity mask
    assert n == len(os.sched_getaffinity(0))


def test_allocated_cpus_is_always_at_least_one():
    # Arrange — a laptop must still get a usable worker count
    env: dict[str, str] = {}
    # Act
    n = allocated_cpus(environ=env)
    # Assert
    assert n >= 1


def test_allocated_cpus_never_exceeds_affinity_on_this_machine():
    # Arrange — the defect in one assertion: the answer must not be the
    # machine's core count when the process is confined to fewer CPUs.
    affinity = len(os.sched_getaffinity(0))
    # Act
    n = allocated_cpus(environ={})
    # Assert
    assert n <= affinity


def test_alloc_snippet_is_single_quote_safe_for_shell_embedding():
    # Arrange — the snippet is embedded as `python -c '<snippet>'`, so a
    # single quote in it would silently truncate the remote command.
    snippet = ALLOCATED_CPUS_PY_SNIPPET
    # Act
    has_single_quote = "'" in snippet
    # Assert
    assert not has_single_quote


def test_alloc_snippet_agrees_with_allocated_cpus_under_slurm_env():
    # Arrange — the shell snippet and the Python function are one policy in
    # two languages; run the real snippet in a real subprocess.
    env = dict(os.environ, SLURM_CPUS_PER_TASK="7")
    # Act
    out = subprocess.run(
        [sys.executable, "-c", ALLOCATED_CPUS_PY_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    # Assert — same answer as the Python implementation
    assert out.stdout.strip() == str(allocated_cpus(environ=env)) == "7"


def _snippet_output_without_slurm_env() -> str:
    """Run the real snippet with every SLURM_* allocation hint stripped."""
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("SLURM_CPUS_PER_TASK", "SLURM_JOB_CPUS_PER_NODE")
    }
    out = subprocess.run(
        [sys.executable, "-c", ALLOCATED_CPUS_PY_SNIPPET],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return out.stdout.strip()


def test_alloc_snippet_matches_python_impl_without_slurm_env():
    # Arrange — no allocation: the two implementations are one policy
    expected = str(allocated_cpus(environ={}))
    # Act
    got = _snippet_output_without_slurm_env()
    # Assert
    assert got == expected


def test_alloc_snippet_lands_on_affinity_without_slurm_env():
    # Arrange — with no Slurm hint the answer must be the affinity mask
    expected = str(len(os.sched_getaffinity(0)))
    # Act
    got = _snippet_output_without_slurm_env()
    # Assert
    assert got == expected


def test_remote_pytest_block_exports_xdist_auto_workers_env():
    # Arrange — the emitted remote command is the actual deliverable
    from scitex_dev._cli.ecosystem._cmds._test_remote import _xdist_pytest_block

    # Act
    block = _xdist_pytest_block("tests/")
    # Assert — `-n auto` is corrected at its source: the env var xdist
    # consults BEFORE psutil is exported for the run.
    assert f"export {XDIST_AUTO_WORKERS_ENV}" in block


def test_remote_pytest_block_derives_worker_count_on_the_remote():
    # Arrange — the local box's allocation says nothing about the remote's
    from scitex_dev._cli.ecosystem._cmds._test_remote import _xdist_pytest_block

    # Act
    block = _xdist_pytest_block("tests/")
    # Assert — command substitution runs the policy snippet remotely
    assert f"$(python -c '{ALLOCATED_CPUS_PY_SNIPPET}')" in block


def test_remote_pytest_block_keeps_serial_fallback_without_xdist():
    # Arrange — a remote without xdist must still run the suite
    from scitex_dev._cli.ecosystem._cmds._test_remote import _xdist_pytest_block

    # Act
    block = _xdist_pytest_block("tests/")
    # Assert
    assert "python -m pytest --tb=short tests/" in block


# EOF
