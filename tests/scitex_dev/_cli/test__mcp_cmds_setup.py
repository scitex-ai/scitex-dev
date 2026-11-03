"""Actual setup CLI uses the shared leaf manifest and explicit owned config."""

import json

import click
from click.testing import CliRunner

from scitex_dev._cli._mcp_cmds import register_mcp_commands


def _run(args):
    @click.group()
    def command():
        pass

    register_mcp_commands(command)
    return CliRunner().invoke(command, ["mcp", "install", *args])


def test_json_setup_is_a_normalized_fragment_without_runtime_claim():
    # Arrange
    args = ["--json"]
    # Act
    result = _run(args)
    payload = json.loads(result.stdout)
    observed = (result.exit_code, payload["client_config"]["mcpServers"],
                payload["runtime_verified"], payload["mcp_servers"])
    # Assert
    assert observed == (0, {"scitex-dev": {"command": "scitex-dev", "args": ["mcp", "start"]}},
                        False, payload["client_config"]["mcpServers"])


def test_explicit_config_preview_then_install_preserves_foreign_settings(tmp_path):
    # Arrange
    target = tmp_path / "owned.json"
    target.write_text('{"settings":{"sentinel":"private-owned-sentinel"}}')
    original = target.read_bytes()
    # Act
    preview = _run(["--config", str(target), "--dry-run", "--json"])
    unchanged = target.read_bytes() == original
    installed = _run(["--config", str(target), "--json"])
    config = json.loads(target.read_text())
    observed = (preview.exit_code, unchanged, installed.exit_code,
                config["settings"], set(config["mcpServers"]),
                "private-owned-sentinel" in preview.output + installed.output)
    # Assert
    assert observed == (0, True, 0, {"sentinel": "private-owned-sentinel"}, {"scitex-dev"}, False)


def test_actual_doctor_json_reports_dependency_health_without_false_readiness():
    # Arrange
    import os
    import subprocess
    import sys

    command = [sys.executable, "-m", "scitex_dev", "mcp", "doctor", "--json"]
    # Act
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, env=os.environ.copy())
    payload = json.loads(result.stdout)
    observed = (result.returncode in (0, 2), payload["runtime_verified"],
                payload["client_loaded"],
                (result.returncode == 0) == (payload["status"] == "catalog-available"),
                bool(payload.get("tools_discovered")) == (result.returncode == 0))
    # Assert
    assert observed == (True, False, False, True, True), result.stderr
