"""Actual selected config/state policy is independent of installed metadata."""

import json
import os
import subprocess
from contextlib import contextmanager
from dataclasses import FrozenInstanceError

import pytest

from scitex_dev._core._knobs import set_package_knob
from scitex_dev.exposure import load_exposure_policy


def _files(root, yaml="", state=None):
    config = root / "config.yaml"
    config.write_text(yaml)
    knobs = root / "state.json"
    knobs.write_text(json.dumps(state or {}))
    return config, knobs


def test_unknown_owner_state_only_preferences_are_independent(tmp_path):
    # Arrange
    config, state = _files(
        tmp_path,
        state={"cli": {"unregistered-owner": False}, "mcp": {"other-owner": False}},
    )
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    # Assert
    assert (
        policy.is_enabled("unregistered_owner", "cli"),
        policy.is_enabled("unregistered-owner", "mcp"),
        policy.is_enabled("unregistered-owner", "skills"),
        policy.is_enabled("other-owner", "mcp"),
        policy.is_enabled("other-owner", "cli"),
        policy.is_enabled("entirely-unknown", "cli"),
    ) == (False, True, True, False, True, True)


@pytest.mark.parametrize("surface", ["cli", "mcp", "skills"])
@pytest.mark.parametrize("yaml_enabled,state_enabled", [(False, True), (True, False)])
def test_actual_yaml_and_state_precedence_for_unknown_owner(
    tmp_path, surface, yaml_enabled, state_enabled
):
    # Arrange
    config, state = _files(
        tmp_path,
        f"packages:\n  - name: owned-new-leaf\n    {surface}_enabled: {str(yaml_enabled).lower()}\n",
        {surface: {"owned-new-leaf": state_enabled}},
    )
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    # Assert
    assert policy.is_enabled("owned-new-leaf", surface) is state_enabled


def test_known_package_yaml_cli_false_does_not_change_other_surfaces(tmp_path):
    # Arrange
    config, state = _files(
        tmp_path, "packages:\n  - name: scitex-dev\n    cli_enabled: false\n"
    )
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    # Assert
    assert tuple(
        policy.is_enabled("scitex-dev", kind) for kind in ("cli", "mcp", "skills")
    ) == (False, True, True)


def test_policy_snapshot_does_not_follow_later_state_writes(tmp_path):
    # Arrange
    config, state = _files(tmp_path, state={"cli": {"owned": False}})
    policy = load_exposure_policy(config, knob_state_path=state)
    # Act
    state.write_text('{"cli":{"owned":true}}')
    # Assert
    assert policy.is_enabled("owned", "cli") is False


def test_policy_and_rows_are_frozen(tmp_path):
    # Arrange
    config, state = _files(tmp_path)
    policy = load_exposure_policy(config, knob_state_path=state)
    # Act
    # Assert
    with pytest.raises(FrozenInstanceError):
        policy.preferences = ()


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "[]",
        '{"cli":[]}',
        '{"cli":{"owned":"false"}}',
        '{"mcp":{"owned":0}}',
        '{"skills":{"owned":null}}',
        '{"cli":{"bad/owner":false}}',
        '{"cli":{"OWNED_leaf":true,"owned-leaf":false}}',
    ],
)
def test_malformed_or_conflicting_state_refuses(tmp_path, raw):
    # Arrange
    config, state = _files(tmp_path)
    state.write_text(raw)
    # Act
    # Assert
    with pytest.raises((TypeError, ValueError)):
        load_exposure_policy(config, knob_state_path=state)


@pytest.mark.parametrize("value", ['"false"', "null", "0", "[]"])
def test_cli_yaml_requires_boolean(tmp_path, value):
    # Arrange
    config, state = _files(
        tmp_path, f"packages:\n  - name: owned\n    cli_enabled: {value}\n"
    )
    # Act
    # Assert
    with pytest.raises(TypeError, match="boolean"):
        load_exposure_policy(config, knob_state_path=state)


def test_default_missing_files_do_not_create_state_or_config(tmp_path):
    # Arrange
    config, state = tmp_path / "absent.yaml", tmp_path / "absent.json"
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    # Assert
    assert (policy.is_enabled("new-owner", "cli"), config.exists(), state.exists()) == (
        True,
        False,
        False,
    )


def test_canonical_setter_retains_other_switches(tmp_path):
    # Arrange
    state = tmp_path / "state.json"
    set_package_knob("owned-leaf", "mcp", False, path=state)
    # Act
    set_package_knob("OWNED_leaf", "cli", False, path=state)
    # Assert
    assert json.loads(state.read_text()) == {
        "cli": {"owned-leaf": False},
        "mcp": {"owned-leaf": False},
        "skills": {},
        "test_execution": {},
    }


def test_policy_never_discovers_or_imports_installed_providers(tmp_path):
    # Arrange
    import sys

    from scitex_dev.cli_providers import list_cli_providers

    site = tmp_path / "installed"
    site.mkdir()
    info = site / "poison-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: poison\nVersion: 1.0\n"
    )
    (info / "entry_points.txt").write_text("[scitex.cli]\npoison = none\n")
    (site / "poison.py").write_text("raise RuntimeError('provider imported')\n")
    before = list_cli_providers(path=[site])
    config, state = _files(tmp_path, state={"cli": {"poison": True}})
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    after = list_cli_providers(path=[site])
    # Assert
    assert (
        before == after,
        after[0].status,
        policy.is_enabled("poison", "cli"),
        "poison" in sys.modules,
    ) == (True, "none", True, False)


@pytest.mark.parametrize(
    "content",
    [
        "[",
        "[]",
        "packages:\n  - name: owned\n    cli_enabled: false\n    pypi_name: ../bad",
    ],
)
def test_malformed_yaml_or_owner_refuses(tmp_path, content):
    # Arrange
    config, state = _files(tmp_path, content)
    # Act
    # Assert
    with pytest.raises((TypeError, ValueError)):
        load_exposure_policy(config, knob_state_path=state)


def test_policy_query_never_reopens_deleted_config_or_state(tmp_path):
    # Arrange
    config, state = _files(tmp_path, state={"cli": {"owned": False}})
    policy = load_exposure_policy(config, knob_state_path=state)
    config.unlink()
    state.unlink()
    # Act
    values = tuple(
        policy.is_enabled("owned", kind) for kind in ("cli", "mcp", "skills")
    )
    # Assert
    assert values == (False, True, True)


def test_legacy_null_packages_keeps_supported_defaults(tmp_path):
    # Arrange
    config, state = _files(tmp_path, "packages: null")
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    # Assert
    assert policy.is_enabled("unconfigured-owner", "cli") is True


@contextmanager
def _selected_environment(root, state, selected, *, cwd=None):
    values = {
        "SCITEX_DIR": str(root),
        "SCITEX_DEV_KNOB_STATE": str(state),
        "SCITEX_DEV_CONFIG": str(selected) if selected is not None else None,
    }
    prior = {key: os.environ.get(key) for key in values}
    prior_cwd = os.getcwd()
    try:
        os.chdir(cwd or root.parent)
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        os.chdir(prior_cwd)
        for key, value in prior.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.mark.parametrize(
    "selected,explicit,expected",
    [(None, None, False), ("env", None, True), ("env", "explicit", False)],
)
def test_actual_config_file_selection_default_env_then_explicit(
    tmp_path, selected, explicit, expected
):
    # Arrange
    root = tmp_path / "scitex"
    default = root / "dev" / "config.yaml"
    default.parent.mkdir(parents=True)
    files = {
        "env": tmp_path / "env.yaml",
        "explicit": tmp_path / "explicit.yaml",
        None: None,
    }
    for path, value in (
        (default, False),
        (files["env"], True),
        (files["explicit"], False),
    ):
        path.write_text(
            f"packages:\n  - name: owned-leaf\n    cli_enabled: {str(value).lower()}\n"
        )
    # Act
    with _selected_environment(root, tmp_path / "absent-state.json", files[selected]):
        policy = load_exposure_policy(files[explicit])
    # Assert
    assert policy.is_enabled("owned-leaf", "cli") is expected


def test_existing_project_scope_still_precedes_user_default(tmp_path):
    # Arrange
    project, user = tmp_path / "project", tmp_path / "user"
    project.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", "--template=", str(project)],
        check=True,
        capture_output=True,
        timeout=10,
    )
    project_config, user_config = (
        project / ".scitex/dev/config.yaml",
        user / "dev/config.yaml",
    )
    for path, value in ((project_config, False), (user_config, True)):
        path.parent.mkdir(parents=True)
        path.write_text(
            f"packages:\n  - name: owned-leaf\n    cli_enabled: {str(value).lower()}\n"
        )
    # Act
    with _selected_environment(user, tmp_path / "absent.json", None, cwd=project):
        policy = load_exposure_policy()
    # Assert
    assert policy.is_enabled("owned-leaf", "cli") is False


@pytest.mark.parametrize("which", ["config", "state"])
def test_non_file_policy_paths_refuse_instead_of_empty_defaults(tmp_path, which):
    # Arrange
    config, state = _files(tmp_path)
    paths = {"config": config, "state": state}
    paths[which].unlink()
    paths[which].mkdir()
    # Act
    # Assert
    with pytest.raises(ValueError):
        load_exposure_policy(config, knob_state_path=state)


def test_cli_writer_preserves_other_surface_identity_keys_and_values(tmp_path):
    # Arrange
    original = {
        "mcp": {"MCP_owner": False},
        "skills": {"SKILL_owner": True},
        "test_execution": {"other": "remote-required"},
    }
    state = tmp_path / "state.json"
    state.write_text(json.dumps(original))
    # Act
    set_package_knob("cli-owner", "cli", False, path=state)
    after = json.loads(state.read_text())
    # Assert
    assert {kind: after[kind] for kind in original} == original
