#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev: Shared developer utilities for the SciTeX ecosystem.

Zero-dependency package providing:
- Docs aggregation and serving across all scitex packages
- Unified search across APIs, CLI, MCP tools, and documentation
- Version management and ecosystem registry
- Bulk rename with cross-reference updates
- LLM-friendly types (Result, ErrorCode, @supports_return_as)

Public API (20 functions)::

    # Docs
    get_docs, build_docs, search_docs

    # Search
    search

    # Versions
    list_versions, check_versions, get_mismatches, fix_mismatches

    # LLM-friendly types
    Result, ErrorCode, supports_return_as, SideEffect,
    classify_exception, handle_result, run_as_cli, run_as_mcp,
    result_to_mcp, wrap_as_mcp
"""

from __future__ import annotations

try:
    from importlib.metadata import version as _v, PackageNotFoundError

    try:
        __version__ = _v("scitex-dev")
    except PackageNotFoundError:
        __version__ = "0.0.0+local"
    del _v, PackageNotFoundError
except ImportError:  # pragma: no cover — only on ancient Pythons
    __version__ = "0.0.0+local"
# PEP 562 lazy public API.
#
# Every public name is loaded on first attribute access — `import scitex_dev`
# costs ~50ms (down from 8.4s) because nothing transitively pulls in the
# `scitex` umbrella, `figrecipe`, `scitex_scholar`, etc. until you actually
# touch a function that needs them. This makes CLI tab-completion, --help,
# and quick scripts an order of magnitude faster.
#
# To add a new public name: extend `_LAZY_ATTRS`. Don't add `from .X import Y`
# at module top — that re-introduces eager loading and slows every CLI call.
# See `_skills/general/03_interface_02_cli/17_lazy-imports-cli-startup.md`.
_LAZY_ATTRS: dict[str, str] = {
    # cli_utils
    "add_dry_run_argument": "cli_utils",
    "add_json_argument": "cli_utils",
    "dry_run_option": "cli_utils",
    "handle_result": "cli_utils",
    "json_option": "cli_utils",
    "run_as_cli": "cli_utils",
    "wrap_as_cli": "cli_utils",
    # decorators
    "supports_return_as": "decorators",
    # errors
    "ErrorCode": "errors",
    "ScitexError": "errors",
    "classify_exception": "errors",
    # _imports
    "InstallHint": "_imports",
    "last_install_hint": "_imports",
    "try_import_optional": "_imports",
    # _mcp
    "get_tools_sync": "_mcp",
    "async_wrap_as_mcp": "_mcp",
    "result_to_mcp": "_mcp",
    "run_as_mcp": "_mcp",
    "wrap_as_mcp": "_mcp",
    # side_effects
    "SideEffect": "side_effects",
    # types
    "RESULT_SCHEMA": "types",
    "Result": "types",
    # docs
    "build_docs": "docs",
    "get_docs": "docs",
    "search_docs": "docs",
    # search
    "search": "search",
    # versions
    "check_versions": "versions",
    "get_ecosystem_versions": "versions",
    "get_mismatches": "versions",
    "list_versions": "versions",
    # fix
    "bump_version": "fix",
    "detect_mismatches": "fix",
    "determine_bump_type": "fix",
    "fix_init_version": "fix",
    "fix_local": "fix",
    "fix_mismatches": "fix",
    "fix_remote": "fix",
    "verify_versions": "fix",
    # config
    "DevConfig": "config",
    "GitHubRemote": "config",
    "HostConfig": "config",
    "PackageConfig": "config",
    "PyPIAccount": "config",
    "config_to_dict": "config",
    "create_default_config": "config",
    "get_config_path": "config",
    "get_enabled_hosts": "config",
    "get_enabled_remotes": "config",
    "load_config": "config",
    # ecosystem
    "ECOSYSTEM": "_ecosystem",
    "get_all_packages": "_ecosystem",
    "get_local_path": "_ecosystem",
    # rtd
    "check_all_rtd": "rtd",
    "check_rtd_status": "rtd",
    # _pypi_package_data
    "PackageDataAuditReport": "_pypi_package_data",
    "audit_package_data": "_pypi_package_data",
    # github
    "check_all_remotes": "github",
    "compare_with_local": "github",
    "get_github_latest_tag": "github",
    "get_github_release": "github",
    "get_github_tags": "github",
    # rename
    "RenameConfig": "rename",
    "RenameResult": "rename",
    "bulk_rename": "rename",
    "execute_rename": "rename",
    "preview_rename": "rename",
    # ssh
    "check_all_hosts": "ssh",
    "get_remote_version": "ssh",
    "get_remote_versions": "ssh",
    "test_host_connection": "ssh",
    # sync
    "sync_all": "_sync",
    "sync_host": "_sync",
    "sync_local": "_sync",
    "sync_tags": "_sync",
    # sync_remote
    "pull_local": "_sync",
    "remote_commit": "_sync",
    "remote_diff": "_sync",
    # ci
    "CIStatus": "ci",
    "WorkflowRun": "ci",
    "check_ci": "ci",
    "check_pypi_publish": "ci",
    "create_github_release": "ci",
    "get_failing_packages": "ci",
    "verify_all_pypi_configs": "ci",
    "verify_pypi_config": "ci",
    "wait_all_pypi": "ci",
    "wait_for_workflow": "ci",
    # deploy
    "deploy_scitex_cloud": "deploy",
    "verify_production": "deploy",
    # skills
    "verify_docs_and_skills": "skills",
    # test_runner
    "TestConfig": "test_runner",
    "fetch_hpc_result": "test_runner",
    "poll_hpc_job": "test_runner",
    "run_hpc_sbatch": "test_runner",
    "run_hpc_srun": "test_runner",
    "run_local": "test_runner",
    "sync_to_hpc": "test_runner",
    "watch_hpc_job": "test_runner",
}


# Editable-install drift warning — fires once per process when the working
# tree is ahead of/behind the latest tag. Cheap (~1ms cache hit; skipped
# entirely on non-editable installs). Suppress with SCITEX_DEV_NO_DRIFT_WARN=1.
try:
    from ._check_editable_drift import emit_if_drift as _emit_drift

    _emit_drift("scitex-dev")
except Exception:
    pass


def __getattr__(name: str):
    """PEP 562 lazy-loader: import on first access, cache, then return."""
    mod_name = _LAZY_ATTRS.get(name)
    if mod_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    attr = getattr(import_module(f".{mod_name}", __name__), name)
    globals()[name] = (
        attr  # cache in module globals; subsequent access skips this branch
    )
    return attr


def __dir__() -> list[str]:
    return sorted(set(_LAZY_ATTRS) | set(globals()))


__all__ = [
    # Version
    "__version__",
    # Docs
    "get_docs",
    "build_docs",
    "search_docs",
    # Search
    "search",
    # Versions
    "list_versions",
    "check_versions",
    "get_mismatches",
    "fix_mismatches",
    "get_ecosystem_versions",
    # LLM-friendly types
    "Result",
    "RESULT_SCHEMA",
    "ErrorCode",
    "ScitexError",
    "classify_exception",
    "try_import_optional",
    "last_install_hint",
    "InstallHint",
    "supports_return_as",
    "SideEffect",
    "handle_result",
    "run_as_cli",
    "wrap_as_cli",
    "run_as_mcp",
    "wrap_as_mcp",
    "async_wrap_as_mcp",
    "result_to_mcp",
    # CLI option factories
    "json_option",
    "dry_run_option",
    "add_json_argument",
    "add_dry_run_argument",
    # Sync
    "sync_all",
    "sync_host",
    "sync_local",
    "sync_tags",
    "remote_diff",
    "remote_commit",
    "pull_local",
]
