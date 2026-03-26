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

__version__ = "0.5.4"

# --- Public API: LLM-friendly types and utilities ---
from .cli_utils import (
    add_dry_run_argument,
    add_json_argument,
    dry_run_option,
    handle_result,
    json_option,
    run_as_cli,
    wrap_as_cli,
)
from .decorators import supports_return_as
from .errors import ErrorCode, classify_exception
from ._mcp_compat import get_tools_sync
from .mcp_utils import async_wrap_as_mcp, result_to_mcp, run_as_mcp, wrap_as_mcp
from .side_effects import SideEffect
from .types import RESULT_SCHEMA, Result

# --- Public API: Docs aggregation ---
from .docs import build_docs, get_docs, search_docs

# --- Public API: Unified search ---
from .search import search

# --- Public API: Versions ---
from .versions import check_versions, get_mismatches, list_versions
from .fix import (
    bump_version as bump_version,
    detect_mismatches as detect_mismatches,
    determine_bump_type as determine_bump_type,
    fix_init_version as fix_init_version,
    fix_local as fix_local,
    fix_mismatches as fix_mismatches,
    fix_remote as fix_remote,
    verify_versions as verify_versions,
)

# --- Accessible but not in __all__ (advanced/internal use) ---

# Config
from .config import (
    DevConfig as DevConfig,
    GitHubRemote as GitHubRemote,
    HostConfig as HostConfig,
    PackageConfig as PackageConfig,
    PyPIAccount as PyPIAccount,
    config_to_dict as config_to_dict,
    create_default_config as create_default_config,
    get_config_path as get_config_path,
    get_enabled_hosts as get_enabled_hosts,
    get_enabled_remotes as get_enabled_remotes,
    load_config as load_config,
)

# Ecosystem
from .ecosystem import (
    ECOSYSTEM as ECOSYSTEM,
    get_all_packages as get_all_packages,
    get_local_path as get_local_path,
)

# RTD
from .rtd import check_all_rtd as check_all_rtd, check_rtd_status as check_rtd_status

# GitHub
from .github import (
    check_all_remotes as check_all_remotes,
    compare_with_local as compare_with_local,
    get_github_latest_tag as get_github_latest_tag,
    get_github_release as get_github_release,
    get_github_tags as get_github_tags,
)

# Rename
from .rename import (
    RenameConfig as RenameConfig,
    RenameResult as RenameResult,
    bulk_rename as bulk_rename,
    execute_rename as execute_rename,
    preview_rename as preview_rename,
)

# SSH
from .ssh import (
    check_all_hosts as check_all_hosts,
    get_remote_version as get_remote_version,
    get_remote_versions as get_remote_versions,
    test_host_connection as test_host_connection,
)

# Sync
from .sync import (
    sync_all as sync_all,
    sync_host as sync_host,
    sync_local as sync_local,
    sync_tags as sync_tags,
)
from .sync_remote import (
    pull_local as pull_local,
    remote_commit as remote_commit,
    remote_diff as remote_diff,
)

# CI
from .ci import (
    CIStatus as CIStatus,
    WorkflowRun as WorkflowRun,
    check_ci as check_ci,
    check_pypi_publish as check_pypi_publish,
    create_github_release as create_github_release,
    get_failing_packages as get_failing_packages,
    verify_all_pypi_configs as verify_all_pypi_configs,
    verify_pypi_config as verify_pypi_config,
    wait_all_pypi as wait_all_pypi,
    wait_for_workflow as wait_for_workflow,
)

# Deploy
from .deploy import (
    deploy_scitex_cloud as deploy_scitex_cloud,
    verify_production as verify_production,
)

# Skills verification
from .skills import verify_docs_and_skills as verify_docs_and_skills

# Test runner
from .test_runner import (
    TestConfig as TestConfig,
    fetch_hpc_result as fetch_hpc_result,
    poll_hpc_job as poll_hpc_job,
    run_hpc_sbatch as run_hpc_sbatch,
    run_hpc_srun as run_hpc_srun,
    run_local as run_local,
    sync_to_hpc as sync_to_hpc,
    watch_hpc_job as watch_hpc_job,
)


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
    # LLM-friendly types
    "Result",
    "RESULT_SCHEMA",
    "ErrorCode",
    "classify_exception",
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
]
