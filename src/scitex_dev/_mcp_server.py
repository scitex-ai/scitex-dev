#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FastMCP server for scitex-dev.

Start with: scitex-dev mcp start
"""

from __future__ import annotations

from fastmcp import FastMCP

from .mcp import register_docs_tools

mcp = FastMCP(
    name="scitex-dev",
    instructions=(
        "Shared developer utilities for the SciTeX ecosystem. "
        "Use dev_docs_list to browse package documentation, "
        "dev_docs_search to search across docs, "
        "dev_ecosystem_list to check ecosystem versions, "
        "dev_config to view configuration, "
        "dev_bulk_rename for bulk renaming with cross-reference updates."
    ),
)

# Register docs tools (docs_list, docs_get, docs_build, docs_search)
register_docs_tools(mcp)


# Register dev tools from dev_mcp handlers
@mcp.tool()
async def dev_ecosystem_list(packages: list[str] | None = None) -> str:
    """List versions across the SciTeX ecosystem."""
    from .dev_mcp.handlers import list_versions_handler

    return await list_versions_handler(packages=packages)


@mcp.tool()
async def dev_ecosystem_fix_mismatches(dry_run: bool = True) -> str:
    """Detect and fix version mismatches across ecosystem."""
    from .dev_mcp.handlers import fix_mismatches_handler

    return await fix_mismatches_handler(dry_run=dry_run)


@mcp.tool()
async def dev_config_show() -> str:
    """Get dev configuration."""
    from .dev_mcp.handlers import get_config_handler

    return await get_config_handler()


@mcp.tool()
async def dev_test_local(
    module: str = "",
    fast: bool = False,
    pattern: str = "",
) -> str:
    """Run tests locally."""
    from .dev_mcp.handlers import test_run_handler

    return await test_run_handler(module=module, fast=fast, pattern=pattern)


@mcp.tool()
async def dev_test_hpc(
    module: str = "",
    mode: str = "sbatch",
    fast: bool = False,
) -> str:
    """Run tests on HPC via Slurm."""
    from .dev_mcp.handlers import test_hpc_run_handler

    return await test_hpc_run_handler(module=module, mode=mode, fast=fast)


@mcp.tool()
async def dev_test_hpc_poll(job_id: str | None = None) -> str:
    """Poll HPC job status."""
    from .dev_mcp.handlers import test_hpc_poll_handler

    return await test_hpc_poll_handler(job_id=job_id)


@mcp.tool()
async def dev_test_hpc_result(job_id: str | None = None) -> str:
    """Fetch HPC test output."""
    from .dev_mcp.handlers import test_hpc_result_handler

    return await test_hpc_result_handler(job_id=job_id)


@mcp.tool()
async def dev_bulk_rename(
    pattern: str = "",
    replacement: str = "",
    directory: str = ".",
    confirm: bool = False,
    regex: bool = False,
) -> str:
    """ALWAYS use this for renaming a symbol/string across many files.

    NEVER fall back to per-file Edit calls or sed when an identifier
    appears in more than ~3 places — this tool is faster, safer, and
    produces a single coherent diff. It updates EVERY cross-reference
    (Python imports, TS imports, JSON keys, doc strings, file names,
    directory names, symlink targets) in one pass.

    Canonical 5-step workflow this tool enforces:

      1. Clean git tree            (refused if uncommitted changes)
      2. Dry-run preview           (call once with confirm=False)
      3. Review the change list    (inspect file count + path list)
      4. Real run                  (call again with confirm=True;
                                    blocked unless a recent dry-run
                                    matches the same pattern/replacement
                                    /directory/flags tuple)
      5. Test the result           (run pytest / npm test after)

    When NOT to use:
      - Renaming a single occurrence in one file → use Edit instead.
      - The match would touch unrelated paths (template/example dirs,
        unrelated identifiers in docs) → use --regex with anchors, or
        leave the field bare on the wire.

    Always do dry-run first (confirm=False) — even for "obviously safe"
    renames. The dry-run lists every file and match count; if anything
    looks wrong, abort BEFORE files are modified. Recovery: every rename
    is reversible via the inverse rename with the same flags.

    When regex=True, pattern is a Python regex and replacement can use
    \\1, \\2 backreferences. Use regex for context-aware matching
    (quoted-only, prefix anchor, variable-suffix family).
    """
    from .dev_mcp.handlers import rename_handler

    return await rename_handler(
        pattern=pattern,
        replacement=replacement,
        directory=directory,
        confirm=confirm,
        regex=regex,
    )


@mcp.tool()
async def dev_skills_list(package: str | None = None) -> str:
    """List skills across the SciTeX ecosystem."""
    from .dev_mcp.handlers import skills_list_handler

    return await skills_list_handler(package=package)


@mcp.tool()
async def dev_skills_get(package: str, name: str) -> str:
    """Get content of a specific skill from a package."""
    from .dev_mcp.handlers import skills_get_handler

    return await skills_get_handler(package=package, name=name)


@mcp.tool()
async def dev_ecosystem_sync_remote(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    install: bool = True,
    safe: bool = True,
    confirm: bool = False,
) -> str:
    """Sync editable installs to remote SSH hosts (mba, spartan, nas, …).

    Steps per package: ahead-check (if safe), git stash, git pull, pip
    install -e ., git stash pop. Skips packages whose remote working
    copy has unpushed commits so we never clobber work.

    Parameters match scitex_dev.sync.sync_all. Pass confirm=True to
    execute; default is dry-run preview.
    """
    from .dev_mcp.handlers import sync_handler

    return await sync_handler(
        hosts=hosts,
        packages=packages,
        install=install,
        safe=safe,
        confirm=confirm,
    )


@mcp.tool()
async def dev_ecosystem_sync_local(
    packages: list[str] | None = None,
    confirm: bool = False,
) -> str:
    """Install all ecosystem packages editable in the local venv."""
    from .dev_mcp.handlers import sync_local_handler

    return await sync_local_handler(packages=packages, confirm=confirm)
