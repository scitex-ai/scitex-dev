"""Shared MCP setup primitives; leaves supply their own launch definition.

Only compatible JSON client configuration is handled here. Writing configuration
neither starts a server nor proves a client loaded or authorized it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from collections.abc import Mapping, Sequence

from packaging.utils import canonicalize_name

__all__ = ["build_mcp_install_manifest", "install_mcp_client_config"]


def build_mcp_install_manifest(
    package: str, *, command: str, args: Sequence[str],
    verify: Sequence[Sequence[str]] = (), server_name: str | None = None,
) -> dict:
    """Normalize explicit leaf launch data, without importing or starting it."""
    package = canonicalize_name(package, validate=True)
    name = package if server_name is None else server_name
    if any(isinstance(cmd, (str, bytes)) for cmd in verify):
        raise ValueError("MCP verification commands must be argument sequences")
    for value in (package, name, command, *args, *(item for cmd in verify for item in cmd)):
        if not isinstance(value, str) or not value or "\0" in value:
            raise ValueError("MCP launch metadata must contain nonempty strings")
    if isinstance(args, (str, bytes)):
        raise ValueError("MCP args must be a sequence of arguments, not shell text")
    return {
        "schema_version": "scitex-mcp-install/1",
        "package": package,
        "transport": "stdio",
        "client_config": {"mcpServers": {
            name: {"command": command, "args": list(args)},
        }},
        "verify_commands": [list(cmd) for cmd in verify],
        "runtime_verified": False,
    }


def _read_config(path: Path) -> tuple[dict, bytes | None, int]:
    if path.is_symlink():
        raise ValueError("MCP config must be an explicit regular file, not a symlink")
    if not path.exists():
        return {}, None, 0o600
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("MCP config must be a regular JSON file of at most 1 MiB")
    raw = path.read_bytes()
    config = json.loads(raw)
    if not isinstance(config, dict) or not isinstance(config.get("mcpServers", {}), dict):
        raise ValueError("MCP config and mcpServers must be JSON objects")
    return config, raw, path.stat().st_mode & 0o777


def _merge(config: dict, fragment: Mapping) -> tuple[dict, bool]:
    servers = fragment.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        raise ValueError("MCP fragment must declare nonempty mcpServers")
    for name, declaration in servers.items():
        if not isinstance(name, str) or not name or not isinstance(declaration, dict):
            raise ValueError("MCP server names and declarations must be valid objects")
        command = declaration.get("command")
        args = declaration.get("args", [])
        if (not isinstance(command, str) or not command or "\0" in command
                or not isinstance(args, list)
                or not all(isinstance(arg, str) and "\0" not in arg for arg in args)):
            raise ValueError("MCP stdio declarations need a command and argument list")
    existing = config.get("mcpServers", {})
    for name, declaration in servers.items():
        if name in existing and existing[name] != declaration:
            raise ValueError(f"MCP server {name!r} already has different configuration")
    merged = {**config, "mcpServers": {**existing, **servers}}
    return merged, merged != config


def install_mcp_client_config(
    fragment: Mapping, destination: str | Path, *, dry_run: bool = False
) -> dict:
    """Merge a leaf fragment without overwriting conflicting/foreign entries.

    Dry runs write nothing. Actual writes are atomic, serialized with this
    installer's per-file lock, and recheck the input before replacement.
    Other writers must coordinate on the same lock to exclude all races.
    Existing values (which may hold credentials) are never returned.
    """
    path = Path(destination).expanduser()
    config, original, mode = _read_config(path)
    merged, changed = _merge(config, fragment)
    result = {"destination": str(path), "servers": sorted(fragment["mcpServers"]),
              "changed": changed, "dry_run": dry_run,
              "scope": "configuration-only", "runtime_verified": False}
    if dry_run:
        return result

    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name("." + path.name + ".scitex-mcp.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    temporary = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        config, original, mode = _read_config(path)
        merged, changed = _merge(config, fragment)
        result["changed"] = changed
        if not changed:
            return result
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.fchmod(stream.fileno(), mode)
            stream.write((json.dumps(merged, indent=2) + "\n").encode())
            stream.flush()
            os.fsync(stream.fileno())
        _, current, _ = _read_config(path)
        if current != original:
            raise ValueError("MCP config changed during installation; no replacement written")
        os.replace(temporary, path)
        temporary = None
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        os.close(fd)
