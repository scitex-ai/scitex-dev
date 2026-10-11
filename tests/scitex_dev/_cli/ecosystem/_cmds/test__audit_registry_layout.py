"""The registry command audits every host package once, without changing Git."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem._cmds._audit_registry_layout import register


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _host_tree(tmp_path: Path, *, name: str = "dotfiles") -> tuple[Path, Path]:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "develop")
    root = repo / "src" / ".scitex"
    root.mkdir(parents=True)
    return repo, root


def _runtime(root: Path, package: str, *, ignored: bool) -> Path:
    runtime = root / package / "runtime"
    runtime.mkdir(parents=True)
    if ignored:
        (runtime / ".gitignore").write_text("*\n", encoding="utf-8")
    (runtime / "state.json").write_text("host-local\n", encoding="utf-8")
    return runtime


def _command() -> click.Group:
    group = click.Group()
    register(group)
    return group


def test_registry_command_reports_missing_policy_across_all_packages(tmp_path):
    # Arrange
    _, root = _host_tree(tmp_path)
    runtimes = [
        _runtime(root, pkg, ignored=False) for pkg in ("agent-container", "dev")
    ]
    command = _command()
    # Act
    result = CliRunner().invoke(
        command, ["audit-registry-layout", "--scitex-dir", str(root), "--json"]
    )
    payload = json.loads(result.output)
    findings = [
        (item["rule"], item["where"], item["severity"])
        for item in payload["violations"]
    ]
    # Assert
    assert (result.exit_code, payload["errors"], findings) == (
        1,
        2,
        [("PS-234", str(runtime / ".gitignore"), "E") for runtime in runtimes],
    )


def test_registry_command_keeps_shared_configuration_tracked(tmp_path):
    # Arrange
    repo, root = _host_tree(tmp_path)
    _runtime(root, "agent-container", ignored=True)
    config = root / "agent-container" / "config.yaml"
    config.write_text("shared: true\n", encoding="utf-8")
    _git(repo, "add", str(config.relative_to(repo)))
    before = _git(repo, "ls-files").stdout.splitlines()
    command = _command()
    # Act
    result = CliRunner().invoke(
        command, ["audit-registry-layout", "--scitex-dir", str(root), "--json"]
    )
    payload = json.loads(result.output)
    after = _git(repo, "ls-files").stdout.splitlines()
    # Assert
    assert (result.exit_code, payload["violations"], before, after) == (
        0,
        [],
        ["src/.scitex/agent-container/config.yaml"],
        ["src/.scitex/agent-container/config.yaml"],
    )


def test_registry_command_refuses_already_tracked_runtime_data(tmp_path):
    # Arrange
    repo, root = _host_tree(tmp_path)
    runtime = _runtime(root, "logging", ignored=False)
    _git(repo, "add", str(runtime.relative_to(repo)))
    (runtime / ".gitignore").write_text("*\n", encoding="utf-8")
    command = _command()
    # Act
    result = CliRunner().invoke(
        command, ["audit-registry-layout", "--scitex-dir", str(root), "--json"]
    )
    payload = json.loads(result.output)
    findings = [
        (item["rule"], item["where"], item["severity"])
        for item in payload["violations"]
    ]
    # Assert
    assert (result.exit_code, findings) == (1, [("PS-234", str(runtime), "E")])


def test_explicit_registry_root_overrides_the_ambient_user_tree(tmp_path):
    # Arrange
    _, explicit_root = _host_tree(tmp_path, name="explicit")
    _, ambient_root = _host_tree(tmp_path, name="ambient")
    _runtime(explicit_root, "dev", ignored=True)
    _runtime(ambient_root, "dev", ignored=False)
    command = _command()
    # Act
    result = CliRunner().invoke(
        command,
        ["audit-registry-layout", "--scitex-dir", str(explicit_root), "--json"],
        env={"SCITEX_DIR": str(ambient_root)},
    )
    payload = json.loads(result.output)
    # Assert
    assert (result.exit_code, payload["scitex_dir"], payload["violations"]) == (
        0,
        str(explicit_root),
        [],
    )


def test_registry_help_describes_layout_and_runtime_rules():
    # Arrange
    command = _command()
    # Act
    result = CliRunner().invoke(command, ["audit-registry-layout", "--help"])
    # Assert
    assert (result.exit_code, "PS-181" in result.output, "PS-234" in result.output) == (
        0,
        True,
        True,
    )


def test_clean_registry_human_result_names_both_rules(tmp_path):
    # Arrange
    _, root = _host_tree(tmp_path)
    _runtime(root, "dev", ignored=True)
    command = _command()
    # Act
    result = CliRunner().invoke(
        command, ["audit-registry-layout", "--scitex-dir", str(root)]
    )
    # Assert
    assert (result.exit_code, "no PS-181 or PS-234 findings" in result.output) == (
        0,
        True,
    )
