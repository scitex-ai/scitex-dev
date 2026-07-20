#!/usr/bin/env python3
"""Tests for the host/scheduler-agnostic test-execution recipe.

Pins the recipe schema (default mode=local), YAML load, submit-template
rendering, the guard decision (remote-required + marker-env logic), and the
git-scope recipe discovery used by the pytest plugin. No mocks — recipes are
real tmp_path YAML files and env/cwd are passed in explicitly.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._core.test_execution import (
    DEFAULT_MARKER_ENV,
    RECIPE_PATH_ENV,
    TestExecutionConfig,
    _pkg_short,
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


# EOF
