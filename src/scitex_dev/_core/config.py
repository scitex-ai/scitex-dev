#!/usr/bin/env python3
# Timestamp: 2026-02-02
# File: scitex_dev/config.py

"""Configuration management for scitex developer utilities."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scitex_config._ecosystem import local_state

from ._default_config import create_default_config as _write_default_config

# Knob-state layer (skills / mcp / test-execution). Re-exported here so the
# historical ``from scitex_dev._core.config import set_package_knob`` (and the
# private helpers the tests import) keep resolving after the extraction.
from ._knobs import (  # noqa: F401
    _KNOB_KINDS,
    _apply_knob_state,
    _knob_state_path,
    _load_knob_state,
    set_package_knob,
    set_package_test_execution,
)
from .test_execution import DEFAULT_MODE as _DEFAULT_TEST_EXECUTION_MODE


@dataclass
class HostConfig:
    """SSH host configuration."""

    name: str
    hostname: str
    user: str
    role: str = "dev"  # dev, staging, prod, hpc
    enabled: bool = True
    ssh_key: str | None = None
    port: int = 22
    # Sync fields
    python_bin: str = "python3"
    pip_bin: str = "pip"
    remote_base: str = "~/proj"
    # Legacy: explicit allow-list. If empty, host syncs all ecosystem
    # packages (preferred). Kept for backward compat.
    packages: list[str] = field(default_factory=list)
    # New: opt-out list. Packages here are excluded from sync.
    exclude: list[str] = field(default_factory=list)


@dataclass
class GitHubRemote:
    """GitHub remote configuration."""

    name: str
    org: str
    enabled: bool = True


@dataclass
class PyPIAccount:
    """PyPI account configuration."""

    name: str
    enabled: bool = True


@dataclass
class PackageConfig:
    """Package configuration."""

    name: str
    local_path: str
    pypi_name: str
    github_repo: str | None = None
    import_name: str | None = None
    # Per-leaf progressive-disclosure knobs, centrally managed by scitex-dev
    # (operator directive 2026-07-20). When False, scitex-dev's aggregators
    # treat the package's skills / MCP server as OFF for context-budget
    # scoping — nothing is uninstalled, it is simply not surfaced.
    skills_enabled: bool = True
    mcp_enabled: bool = True
    # Test-execution policy mode: "local" (allow local pytest) or
    # "remote-required" (local pytest is an ERROR; suite must run remote).
    # Resolved the same way as skills/mcp: ECOSYSTEM default → config.yaml →
    # knob-state.json. The rich recipe (host + submit template + marker env)
    # lives in the package's own config-layout — see _core.test_execution.
    test_execution: str = "local"


@dataclass
class DevConfig:
    """Full developer configuration."""

    packages: list[PackageConfig] = field(default_factory=list)
    hosts: list[HostConfig] = field(default_factory=list)
    github_remotes: list[GitHubRemote] = field(default_factory=list)
    pypi_accounts: list[PyPIAccount] = field(default_factory=list)
    branches: list[str] = field(default_factory=lambda: ["main", "develop"])


def _get_default_config_path() -> Path:
    """Get default config file path.

    Preferred location is ``~/.scitex/dev/config.yaml`` (matches the
    runtime/ sibling tree). The legacy single-file path
    ``~/.scitex/dev_config.yaml`` is honored as a fallback if it exists
    AND the preferred path does not, to keep older installs working.
    """
    preferred = local_state.path("dev", "config.yaml")
    legacy = local_state.user_root() / "dev_config.yaml"
    if not preferred.exists() and legacy.exists():
        return legacy
    return preferred


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML file."""
    if not path.exists():
        return {}

    try:
        import yaml

        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # Fallback: basic YAML parsing for simple configs
        content = path.read_text()
        # Very basic parsing - handles simple key: value pairs
        result: dict[str, Any] = {}
        current_key = None
        current_list: list[Any] = []

        for line in content.split("\n"):
            line = line.rstrip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("  - "):
                # List item
                current_list.append(line[4:].strip())
            elif line.startswith("  "):
                # Nested dict item - skip for basic parsing
                continue
            elif ":" in line:
                if current_key and current_list:
                    result[current_key] = current_list
                    current_list = []
                key, val = line.split(":", 1)
                current_key = key.strip()
                val = val.strip()
                if val:
                    result[current_key] = val
        if current_key and current_list:
            result[current_key] = current_list
        return result
    except Exception:
        return {}


def _parse_host_config(data: dict[str, Any]) -> HostConfig:
    """Parse host config from dict.

    Supports both the legacy ``packages:`` allow-list and the new
    ``exclude:`` opt-out list. If neither is given, the host syncs all
    ecosystem packages.
    """
    packages = data.get("packages", [])
    if isinstance(packages, str):
        packages = [p.strip() for p in packages.split(",") if p.strip()]
    exclude = data.get("exclude", [])
    if isinstance(exclude, str):
        exclude = [p.strip() for p in exclude.split(",") if p.strip()]
    return HostConfig(
        name=data.get("name", "unknown"),
        hostname=data.get("hostname", "localhost"),
        user=data.get("user", os.getenv("USER", "user")),
        role=data.get("role", "dev"),
        enabled=data.get("enabled", True),
        ssh_key=data.get("ssh_key"),
        port=data.get("port", 22),
        python_bin=data.get("python_bin", "python3"),
        pip_bin=data.get("pip_bin", "pip"),
        remote_base=data.get("remote_base", "~/proj"),
        packages=packages if isinstance(packages, list) else [],
        exclude=exclude if isinstance(exclude, list) else [],
    )


def _parse_github_remote(data: dict[str, Any]) -> GitHubRemote:
    """Parse GitHub remote from dict."""
    return GitHubRemote(
        name=data.get("name", "unknown"),
        org=data.get("org", ""),
        enabled=data.get("enabled", True),
    )


def _parse_pypi_account(data: dict[str, Any]) -> PyPIAccount:
    """Parse PyPI account from dict."""
    return PyPIAccount(
        name=data.get("name", ""),
        enabled=data.get("enabled", True),
    )


def _parse_package_config(data: dict[str, Any]) -> PackageConfig:
    """Parse package config from dict."""
    return PackageConfig(
        name=data.get("name", "unknown"),
        local_path=data.get("local_path", ""),
        pypi_name=data.get("pypi_name", data.get("name", "")),
        github_repo=data.get("github_repo"),
        import_name=data.get("import_name"),
        skills_enabled=bool(data.get("skills_enabled", True)),
        mcp_enabled=bool(data.get("mcp_enabled", True)),
        test_execution=str(data.get("test_execution", _DEFAULT_TEST_EXECUTION_MODE)),
    )


def load_config(config_path: str | Path | None = None) -> DevConfig:
    """Load config from YAML with environment variable overrides.

    Parameters
    ----------
    config_path : str | Path | None
        Path to config file. If None, uses SCITEX_DEV_CONFIG env var
        or ~/.scitex/dev_config.yaml

    Returns
    -------
    DevConfig
        Loaded configuration.
    """
    # Determine config path
    if config_path is None:
        config_path = os.getenv("SCITEX_DEV_CONFIG")
    if config_path is None:
        config_path = _get_default_config_path()
    else:
        config_path = Path(config_path).expanduser()

    # Load YAML
    data = _load_yaml(config_path)

    # Parse packages: ECOSYSTEM is single source of truth, config overrides
    from .._ecosystem import ECOSYSTEM

    # Start with all ECOSYSTEM packages
    pkg_map: dict[str, PackageConfig] = {}
    for name, info in ECOSYSTEM.items():
        pkg_map[name] = PackageConfig(
            name=name,
            local_path=info.get("local_path", ""),
            pypi_name=info.get("pypi_name", name),
            github_repo=info.get("github_repo"),
            import_name=info.get("import_name"),
            skills_enabled=bool(info.get("skills_enabled", True)),
            mcp_enabled=bool(info.get("mcp_enabled", True)),
            test_execution=str(
                info.get("test_execution", _DEFAULT_TEST_EXECUTION_MODE)
            ),
        )

    # Override with config file entries (if any)
    if "packages" in data and isinstance(data["packages"], list):
        for pkg_data in data["packages"]:
            if isinstance(pkg_data, dict):
                parsed = _parse_package_config(pkg_data)
                pkg_map[parsed.name] = parsed

    packages = list(pkg_map.values())

    # Overlay machine-managed knob-state (CLI toggles) at highest precedence.
    _apply_knob_state(packages)

    # Parse hosts
    hosts = []
    if "hosts" in data and isinstance(data["hosts"], list):
        for host_data in data["hosts"]:
            if isinstance(host_data, dict):
                hosts.append(_parse_host_config(host_data))

    # Override from env
    env_hosts = os.getenv("SCITEX_DEV_HOSTS", "").strip()
    if env_hosts:
        enabled_names = set(env_hosts.split(","))
        for host in hosts:
            host.enabled = host.name in enabled_names

    # Parse GitHub remotes
    github_remotes = []
    if "github_remotes" in data and isinstance(data["github_remotes"], list):
        for remote_data in data["github_remotes"]:
            if isinstance(remote_data, dict):
                github_remotes.append(_parse_github_remote(remote_data))

    # Default GitHub remote from ecosystem
    if not github_remotes:
        github_remotes.append(GitHubRemote(name="ywatanabe1989", org="ywatanabe1989"))

    # Override from env
    env_remotes = os.getenv("SCITEX_DEV_GITHUB_REMOTES", "").strip()
    if env_remotes:
        enabled_names = set(env_remotes.split(","))
        for remote in github_remotes:
            remote.enabled = remote.name in enabled_names

    # Parse PyPI accounts
    pypi_accounts = []
    if "pypi_accounts" in data and isinstance(data["pypi_accounts"], list):
        for acct_data in data["pypi_accounts"]:
            if isinstance(acct_data, dict):
                pypi_accounts.append(_parse_pypi_account(acct_data))

    if not pypi_accounts:
        pypi_accounts.append(PyPIAccount(name="ywatanabe1989"))

    # Parse branches
    branches = data.get("branches", ["main", "develop"])
    if not isinstance(branches, list):
        branches = ["main", "develop"]

    return DevConfig(
        packages=packages,
        hosts=hosts,
        github_remotes=github_remotes,
        pypi_accounts=pypi_accounts,
        branches=branches,
    )


def get_enabled_hosts(config: DevConfig | None = None) -> list[HostConfig]:
    """Get list of enabled hosts.

    Parameters
    ----------
    config : DevConfig | None
        Configuration to use. If None, loads default config.

    Returns
    -------
    list[HostConfig]
        List of enabled hosts.
    """
    if config is None:
        config = load_config()
    return [h for h in config.hosts if h.enabled]


def get_enabled_remotes(config: DevConfig | None = None) -> list[GitHubRemote]:
    """Get list of enabled GitHub remotes.

    Parameters
    ----------
    config : DevConfig | None
        Configuration to use. If None, loads default config.

    Returns
    -------
    list[GitHubRemote]
        List of enabled remotes.
    """
    if config is None:
        config = load_config()
    return [r for r in config.github_remotes if r.enabled]


def get_enabled_skills(config: DevConfig | None = None) -> list[PackageConfig]:
    """Resolved view: packages whose skills are enabled (progressive-disclosure knob).

    scitex-dev aggregators (skills index, per-agent scoping) consult this so a
    package's skills load into context ONLY when centrally enabled.
    """
    if config is None:
        config = load_config()
    return [p for p in config.packages if p.skills_enabled]


def get_enabled_mcp(config: DevConfig | None = None) -> list[PackageConfig]:
    """Resolved view: packages whose MCP server is enabled (progressive-disclosure knob)."""
    if config is None:
        config = load_config()
    return [p for p in config.packages if p.mcp_enabled]


def get_test_execution_mode(name: str, config: DevConfig | None = None) -> str:
    """Resolved test-execution MODE for package ``name`` (default ``"local"``).

    Reads the fully-resolved ``PackageConfig.test_execution`` (ECOSYSTEM →
    config.yaml → knob-state.json). Unknown packages resolve to the default.
    """
    if config is None:
        config = load_config()
    for p in config.packages:
        if p.name == name:
            return p.test_execution
    return _DEFAULT_TEST_EXECUTION_MODE


def config_to_dict(config: DevConfig, config_path: Path | None = None) -> dict:
    """Serialize a DevConfig to a plain dict for JSON responses.

    Parameters
    ----------
    config : DevConfig
        Configuration to serialize.
    config_path : Path | None
        If provided, included as ``"config_path"`` in the result.

    Returns
    -------
    dict
        Serialized configuration.
    """
    result: dict = {
        "packages": [
            {
                "name": p.name,
                "local_path": p.local_path,
                "pypi_name": p.pypi_name,
                "github_repo": p.github_repo,
                "skills_enabled": p.skills_enabled,
                "mcp_enabled": p.mcp_enabled,
                "test_execution": p.test_execution,
            }
            for p in config.packages
        ],
        "hosts": [
            {
                "name": h.name,
                "hostname": h.hostname,
                "user": h.user,
                "role": h.role,
                "enabled": h.enabled,
            }
            for h in config.hosts
        ],
        "github_remotes": [
            {"name": r.name, "org": r.org, "enabled": r.enabled}
            for r in config.github_remotes
        ],
        "branches": config.branches,
    }
    if config_path is not None:
        result["config_path"] = str(config_path)
    return result


def get_config_path() -> Path:
    """Get the config file path (may not exist)."""
    path = os.getenv("SCITEX_DEV_CONFIG")
    if path:
        return Path(path).expanduser()
    return _get_default_config_path()


def create_default_config() -> Path:
    """Create the default config file at the canonical path if it's absent."""
    return _write_default_config(_get_default_config_path())


# EOF
