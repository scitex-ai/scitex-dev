#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev: Shared developer utilities for the SciTeX ecosystem.

Zero-dependency package providing:
- Docs aggregation and serving across all scitex packages
- Unified search across APIs, CLI, MCP tools, and documentation
- Version management and ecosystem registry
- Bulk rename with cross-reference updates
- Dev sync, SSH, GitHub, and test runner utilities
- CLI and MCP utilities for LLM-friendly interfaces
"""

__version__ = "0.1.0"

# Docs aggregation
from .docs import build_docs, get_docs, search_docs

# Unified search
from .search import search

# Config
from .config import (
    DevConfig,
    GitHubRemote,
    HostConfig,
    PackageConfig,
    PyPIAccount,
    config_to_dict,
    create_default_config,
    get_config_path,
    get_enabled_hosts,
    get_enabled_remotes,
    load_config,
)

# Ecosystem
from .ecosystem import ECOSYSTEM, get_all_packages, get_local_path

# Versions
from .versions import check_versions, get_mismatches, list_versions

# Fix
from .fix import fix_mismatches

# GitHub
from .github import (
    check_all_remotes,
    compare_with_local,
    get_github_latest_tag,
    get_github_release,
    get_github_tags,
)

# Rename
from .rename import (
    RenameConfig,
    RenameResult,
    bulk_rename,
    execute_rename,
    preview_rename,
)

# SSH
from .ssh import (
    check_all_hosts,
    get_remote_version,
    get_remote_versions,
    test_host_connection,
)

# Sync
from .sync import sync_all, sync_host, sync_local, sync_tags
from .sync_remote import pull_local, remote_commit, remote_diff

# Test runner
from .test_runner import (
    TestConfig,
    fetch_hpc_result,
    poll_hpc_job,
    run_hpc_sbatch,
    run_hpc_srun,
    run_local,
    sync_to_hpc,
    watch_hpc_job,
)

__all__ = [
    # Docs
    "get_docs",
    "build_docs",
    "search_docs",
    # Search
    "search",
    # Version
    "__version__",
    # Config
    "load_config",
    "get_config_path",
    "create_default_config",
    "get_enabled_hosts",
    "get_enabled_remotes",
    "config_to_dict",
    "DevConfig",
    "HostConfig",
    "GitHubRemote",
    "PackageConfig",
    "PyPIAccount",
    # Ecosystem
    "ECOSYSTEM",
    "get_all_packages",
    "get_local_path",
    # Versions
    "list_versions",
    "check_versions",
    "get_mismatches",
    # Fix
    "fix_mismatches",
    # GitHub
    "check_all_remotes",
    "compare_with_local",
    "get_github_tags",
    "get_github_latest_tag",
    "get_github_release",
    # Rename
    "bulk_rename",
    "preview_rename",
    "execute_rename",
    "RenameConfig",
    "RenameResult",
    # SSH
    "check_all_hosts",
    "get_remote_version",
    "get_remote_versions",
    "test_host_connection",
    # Sync
    "sync_all",
    "sync_host",
    "sync_local",
    "sync_tags",
    "remote_diff",
    "remote_commit",
    "pull_local",
    # Test
    "run_local",
    "run_hpc_srun",
    "run_hpc_sbatch",
    "poll_hpc_job",
    "fetch_hpc_result",
    "watch_hpc_job",
    "sync_to_hpc",
    "TestConfig",
]
