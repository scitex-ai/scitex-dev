#!/usr/bin/env python3
# Timestamp: 2026-03-13
# File: scitex_dev/dev_mcp/handlers.py

"""MCP handler implementations for developer utilities.

All handlers return structured Result JSON via wrap_as_mcp.
"""

from __future__ import annotations


from ..mcp_utils import wrap_as_mcp
from ..types import Result


async def list_versions_handler(
    packages: list[str] | None = None,
) -> str:
    """List versions across the scitex ecosystem."""
    from ..versions import list_versions

    return wrap_as_mcp(
        list_versions,
        idempotent=True,
        packages=packages,
    )


async def get_config_handler() -> str:
    """Get current developer configuration."""
    from ..config import config_to_dict, get_config_path, load_config

    def _get_config():
        config = load_config()
        return config_to_dict(config, config_path=get_config_path())

    return wrap_as_mcp(
        _get_config,
        idempotent=True,
    )


async def test_run_handler(
    module: str = "",
    fast: bool = False,
    coverage: bool = False,
    exitfirst: bool = True,
    pattern: str = "",
    parallel: str = "auto",
) -> str:
    """Run tests locally."""
    from ..test_runner import TestConfig, run_local

    def _run():
        config = TestConfig(
            module=module,
            fast=fast,
            coverage=coverage,
            exitfirst=exitfirst,
            pattern=pattern,
            parallel=parallel,
        )
        exit_code = run_local(config)
        return {"exit_code": exit_code}

    return wrap_as_mcp(
        _run,
        idempotent=True,
    )


async def test_hpc_run_handler(
    module: str = "",
    fast: bool = False,
    hpc_cpus: int = 8,
    hpc_partition: str = "sapphire",
    hpc_time: str = "00:10:00",
    hpc_mem: str = "16G",
    async_mode: bool = False,
) -> str:
    """Run tests on HPC via Slurm."""
    from ..test_runner import (
        TestConfig,
        _check_ssh,
        _get_hpc_config,
        run_hpc_sbatch,
        run_hpc_srun,
        sync_to_hpc,
    )

    config = TestConfig(
        module=module,
        fast=fast,
        hpc_cpus=hpc_cpus,
        hpc_partition=hpc_partition,
        hpc_time=hpc_time,
        hpc_mem=hpc_mem,
    )
    hpc_cfg = _get_hpc_config(config)
    host = hpc_cfg["host"]

    if not _check_ssh(host):
        return Result(
            success=False,
            error=f"Cannot connect to {host}",
            error_code="E007",
            hints_on_error=[f"Check SSH connectivity to {host}"],
        ).to_json()

    if not sync_to_hpc(config):
        return Result(
            success=False,
            error="rsync failed",
            error_code="E007",
            hints_on_error=["Check rsync and SSH configuration"],
        ).to_json()

    if async_mode:
        job_id = run_hpc_sbatch(config)
        if job_id:
            return Result(
                success=True,
                data={"job_id": job_id, "host": host},
                side_effects=["hpc_job: submits Slurm job on remote HPC"],
            ).to_json()
        return Result(
            success=False,
            error="Failed to submit job",
            error_code="E999",
        ).to_json()
    else:
        exit_code = run_hpc_srun(config)
        return Result(
            success=exit_code == 0,
            data={"exit_code": exit_code, "host": host},
            side_effects=["hpc_job: submits Slurm job on remote HPC"],
        ).to_json()


async def test_hpc_poll_handler(
    job_id: str | None = None,
) -> str:
    """Poll HPC job status."""
    from ..test_runner import poll_hpc_job

    return wrap_as_mcp(
        poll_hpc_job,
        idempotent=True,
        job_id=job_id,
    )


async def test_hpc_result_handler(
    job_id: str | None = None,
) -> str:
    """Fetch full HPC test output."""
    from ..test_runner import fetch_hpc_result

    def _fetch():
        output = fetch_hpc_result(job_id=job_id)
        return {"output": output, "job_id": job_id or "last"}

    return wrap_as_mcp(
        _fetch,
        idempotent=True,
    )


async def sync_handler(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    install: bool = True,
    confirm: bool = False,
) -> str:
    """Sync ecosystem packages to remote hosts."""
    from ..sync import sync_all

    return wrap_as_mcp(
        sync_all,
        side_effects=["remote_exec: git pull + pip install on remote hosts"],
        hosts=hosts,
        packages=packages,
        install=install,
        confirm=confirm,
    )


async def sync_local_handler(
    packages: list[str] | None = None,
    confirm: bool = False,
) -> str:
    """Install all local editable packages."""
    from ..sync import sync_local

    return wrap_as_mcp(
        sync_local,
        side_effects=["pip_install: installs packages in editable mode"],
        packages=packages,
        confirm=confirm,
    )


async def remote_diff_handler(
    host: str | None = None,
    packages: list[str] | None = None,
) -> str:
    """Show git diff on remote host(s)."""
    from ..sync_remote import remote_diff

    return wrap_as_mcp(
        remote_diff,
        idempotent=True,
        host=host,
        packages=packages,
    )


async def remote_commit_handler(
    host: str,
    packages: list[str] | None = None,
    message: str | None = None,
    push: bool = True,
    confirm: bool = False,
) -> str:
    """Commit dirty changes on a remote host."""
    from ..sync_remote import remote_commit

    return wrap_as_mcp(
        remote_commit,
        side_effects=[
            "git_commit: commits changes on remote host",
            "git_push: pushes to origin",
        ],
        host=host,
        packages=packages,
        message=message,
        push=push,
        confirm=confirm,
    )


async def pull_local_handler(
    packages: list[str] | None = None,
    confirm: bool = False,
    stash: bool = True,
) -> str:
    """Pull latest from origin to local repos."""
    from ..sync_remote import pull_local

    return wrap_as_mcp(
        pull_local,
        side_effects=["git_pull: pulls from origin to local repos"],
        packages=packages,
        confirm=confirm,
        stash=stash,
    )


async def rename_handler(
    pattern: str,
    replacement: str,
    directory: str = ".",
    confirm: bool = False,
    regex: bool = False,
    django_safe: bool = True,
    extra_excludes: list[str] | None = None,
    force: bool = False,
    skip_ids: list[str] | None = None,
    use_sudo: bool = False,
    sudo_password: str | None = None,
    scope: str = "",
    recursive: bool = True,
) -> str:
    """Bulk rename files, contents, directories, and symlinks."""
    from dataclasses import asdict

    from ..rename import RenameConfig, bulk_rename
    from ..rename.safety import has_uncommitted_changes

    if confirm and not force and has_uncommitted_changes(directory):
        return Result(
            success=False,
            error="Uncommitted changes detected. Commit or stash first.",
            error_code="E009",
            hints_on_error=[
                "Run 'git commit' or 'git stash' first",
                "Or pass force=True to skip this check",
            ],
        ).to_json()

    if use_sudo and sudo_password:
        from ..rename.io import set_sudo_password

        set_sudo_password(sudo_password)

    def _rename():
        config = RenameConfig(
            pattern=pattern,
            replacement=replacement,
            directory=directory,
            dry_run=not confirm,
            regex=regex,
            django_safe=django_safe,
            scope=scope,
            recursive=recursive,
            extra_excludes=extra_excludes or [],
            skip_ids=skip_ids or [],
            use_sudo=use_sudo,
        )
        result = bulk_rename(config)
        return asdict(result)

    try:
        return wrap_as_mcp(
            _rename,
            side_effects=["file_modify: renames files, directories, and content"],
        )
    finally:
        if use_sudo and sudo_password:
            from ..rename.io import set_sudo_password

            set_sudo_password(None)


async def fix_mismatches_handler(
    hosts: list[str] | None = None,
    packages: list[str] | None = None,
    local: bool = True,
    remote: bool = True,
    confirm: bool = False,
) -> str:
    """Detect and fix version mismatches across the ecosystem."""
    from ..fix import fix_mismatches

    return wrap_as_mcp(
        fix_mismatches,
        side_effects=[
            "pip_install: fixes mismatched package versions",
            "remote_exec: git pull on remote hosts",
        ],
        hosts=hosts,
        packages=packages,
        local=local,
        remote=remote,
        confirm=confirm,
    )


async def skills_list_handler(
    package: str | None = None,
) -> str:
    """List skills across the SciTeX ecosystem."""
    from ..skills import list_skills

    return wrap_as_mcp(list_skills, idempotent=True, package=package)


async def skills_get_handler(
    package: str,
    name: str,
) -> str:
    """Get content of a specific skill."""
    from ..skills import get_skill

    return wrap_as_mcp(get_skill, idempotent=True, package=package, name=name)


# EOF
