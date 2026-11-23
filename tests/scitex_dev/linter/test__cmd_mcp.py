"""MCP informational CLI output uses valid JSON without installing or starting."""

import json

import pytest
from click.testing import CliRunner

from scitex_dev.linter.cli import main_group


@pytest.fixture(params=[
    (kind, as_json, flags)
    for kind in ["normal", "quoted", "missing"]
    for as_json in [False, True]
    for flags in [[], ["--dry-run"], ["--yes"], ["--dry-run", "--yes"]]
])
def installation_case(request, tmp_path):
    kind, as_json, flags = request.param
    directory = tmp_path / ('quoted "and\\backslash' if kind == "quoted" else "bin")
    directory.mkdir()
    command = directory / "scitex-dev"
    selected = "scitex-dev"
    if kind != "missing":
        command.write_text("#!/bin/sh\nexit 0\n")
        command.chmod(0o755)
        selected = str(command)
    expected = {"mcpServers": {"scitex-dev-linter": {
        "command": selected, "args": ["linter", "mcp", "start"],
    }}}
    before = {str(f.relative_to(tmp_path)): (f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns)
              for f in tmp_path.rglob("*") if f.is_file()}
    return tmp_path, as_json, flags, expected, before, {"PATH": str(directory)}


def test_mcp_install_emits_parseable_configuration(installation_case):
    # Arrange
    _, as_json, flags, expected, _, environment = installation_case
    args = ["mcp", "install", *flags] + (["--json"] if as_json else [])
    # Act
    result = CliRunner().invoke(main_group, args, env=environment)
    document = result.stdout if as_json else result.stdout[result.stdout.index("{"):]
    # Assert
    assert (result.exit_code, json.loads(document)) == (0, expected)


def test_mcp_install_preserves_existing_files(installation_case):
    # Arrange
    root, as_json, flags, _, before, environment = installation_case
    args = ["mcp", "install", *flags] + (["--json"] if as_json else [])
    # Act
    CliRunner().invoke(main_group, args, env=environment)
    after = {str(f.relative_to(root)): (f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns)
             for f in root.rglob("*") if f.is_file()}
    # Assert
    assert after == before


@pytest.mark.parametrize("transport", ["stdio", "sse"])
@pytest.mark.parametrize("flags", [[], ["--yes"]])
def test_mcp_start_dry_run_json_describes_intent(transport, flags):
    # Arrange
    expected = {"action": "start", "transport": transport, "dry_run": True}
    # Act
    result = CliRunner().invoke(main_group, ["mcp", "start", "--dry-run", "--json", "--transport", transport, *flags])
    # Assert
    assert (result.exit_code, json.loads(result.stdout)) == (0, expected)
