"""Owned real files exercise safe client setup without running MCP tools."""

import json
from concurrent.futures import ThreadPoolExecutor

from scitex_dev.mcp_setup import build_mcp_install_manifest, install_mcp_client_config


def _manifest(name="owned"):
    return build_mcp_install_manifest(name, command="owned-command", args=["mcp", "start"])


def test_leaf_manifest_is_json_client_compatible():
    # Arrange
    manifest = _manifest()
    # Act
    result = json.loads(json.dumps(manifest))
    # Assert
    assert (result["client_config"], result["runtime_verified"]) == (
        {"mcpServers": {"owned": {"command": "owned-command", "args": ["mcp", "start"]}}}, False
    )


def test_dry_run_creates_neither_parent_config_nor_lock(tmp_path):
    # Arrange
    target = tmp_path / "absent" / ".mcp.json"
    # Act
    result = install_mcp_client_config(_manifest()["client_config"], target, dry_run=True)
    # Assert
    assert (result["changed"], result["dry_run"], target.parent.exists()) == (True, True, False)


def test_install_preserves_foreign_values_and_is_idempotent(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    foreign = {"settings": {"owned-secret-sentinel": "do-not-print"},
               "mcpServers": {"foreign": {"command": "keep", "env": {"KEY": "private-sentinel"}}}}
    target.write_text(json.dumps(foreign))
    # Act
    first = install_mcp_client_config(_manifest()["client_config"], target)
    after = target.read_bytes()
    second = install_mcp_client_config(_manifest()["client_config"], target)
    config = json.loads(after)
    observed = (first["changed"], second["changed"], after == target.read_bytes(),
                config["settings"] == foreign["settings"],
                config["mcpServers"]["foreign"] == foreign["mcpServers"]["foreign"],
                "private-sentinel" in json.dumps(first), "do-not-print" in json.dumps(second))
    # Assert
    assert observed == (True, False, True, True, True, False, False)


def test_same_server_conflict_refuses_before_any_change(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    target.write_text('{"mcpServers":{"owned":{"command":"foreign-command"}}}')
    original = target.read_bytes()
    # Act
    error = None
    try:
        install_mcp_client_config(_manifest()["client_config"], target)
    except ValueError as exc:
        error = str(exc)
    observed = (error is not None and "different configuration" in error,
                target.read_bytes() == original)
    # Assert
    assert observed == (True, True)


def test_invalid_existing_json_is_not_overwritten(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    target.write_text("{not-json")
    # Act
    refused = False
    try:
        install_mcp_client_config(_manifest()["client_config"], target)
    except ValueError:
        refused = True
    observed = (refused, target.read_text())
    # Assert
    assert observed == (True, "{not-json")


def test_concurrent_shared_installs_preserve_both_servers(tmp_path):
    # Arrange
    target = tmp_path / "mcp.json"
    fragments = [_manifest(name)["client_config"] for name in ["owned-a", "owned-b"]]
    # Act
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda fragment: install_mcp_client_config(fragment, target), fragments))
    config = json.loads(target.read_text())
    # Assert
    assert set(config["mcpServers"]) == {"owned-a", "owned-b"}
