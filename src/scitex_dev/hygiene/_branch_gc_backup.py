#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BUNDLE BEFORE DELETE. The ordering IS the contract.

    bundle -> verify -> re-confirm SHAs -> delete

A failure at ANY step aborts the pass with ZERO deletions. There is no
"backup failed but the branches were clearly merged so we proceeded"
path, because that sentence is what every destructive incident sounds
like in hindsight.

Quarantine location follows the ``clean-root`` convention already in this
repo, and is gitignored by the standard ``.scitex/*/runtime/*`` rule::

    <repo>/.scitex/dev/runtime/branch-gc/<YYYYmmddTHHMMSSZ>/
        branches.bundle
        manifest.json

The bundle is SELF-CONTAINED — no ``^base`` exclusions. A thin bundle is
half the size and completely unrestorable if the base it was thinned
against is ever missing, which is precisely the situation a restore
happens in. Correctness over size.

Bundles are NEVER auto-deleted by this primitive. Pruning them is a
separate, explicit, operator-invoked act; a cleanup that reaps its own
undo log has no undo log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from ._branch_gc_model import BranchInfo
from ._branch_gc_probe import branch_sha, run_git

__all__ = [
    "BACKUP_REL_DIR",
    "BUNDLE_NAME",
    "MANIFEST_NAME",
    "BackupResult",
    "create_backup",
    "restore_command_for",
    "sha_still_matches",
]

BACKUP_REL_DIR = Path(".scitex") / "dev" / "runtime" / "branch-gc"
BUNDLE_NAME = "branches.bundle"
MANIFEST_NAME = "manifest.json"


@dataclass(frozen=True)
class BackupResult:
    """A verified bundle, or a stated reason there is none."""

    ok: bool = False
    directory: str = ""
    bundle_path: str = ""
    manifest_path: str = ""
    restore_command: str = ""
    shas: dict = field(default_factory=dict)
    error: str = ""


def restore_command_for(repo: str | Path, bundle_path: str | Path) -> str:
    """The literal command that puts every bundled branch back.

    Printed in the report and written into the manifest. A backup whose
    restore procedure is "figure out git bundle" is not a backup an
    operator can use at 3am.
    """
    return f"git -C {repo} fetch {bundle_path} 'refs/heads/*:refs/heads/*'"


def _timestamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def create_backup(
    repo: str | Path,
    branches: Sequence[BranchInfo],
    *,
    config_snapshot: dict | None = None,
    keep_report: dict | None = None,
    now: datetime | None = None,
) -> BackupResult:
    """Bundle ``branches``, VERIFY the bundle, then write the manifest.

    Returns ``ok=False`` with a stated ``error`` if anything at all went
    wrong — missing bundle, zero-length bundle, ``git bundle verify``
    non-zero. The caller must treat that as "delete nothing".
    """
    if not branches:
        return BackupResult(ok=False, error="no branches to back up")

    repo_path = Path(repo)
    directory = repo_path / BACKUP_REL_DIR / _timestamp(now)
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return BackupResult(ok=False, error=f"cannot create {directory}: {exc}")

    bundle_path = directory / BUNDLE_NAME
    names = [info.name for info in branches]
    ok, detail = run_git(repo_path, "bundle", "create", str(bundle_path), *names)
    if not ok:
        return BackupResult(
            ok=False,
            directory=str(directory),
            error=f"git bundle create failed: {detail}",
        )

    if not bundle_path.is_file() or bundle_path.stat().st_size == 0:
        return BackupResult(
            ok=False,
            directory=str(directory),
            bundle_path=str(bundle_path),
            error="bundle is missing or zero-length after create",
        )

    verified, verify_detail = run_git(
        repo_path, "bundle", "verify", str(bundle_path), merge_stderr=True
    )
    if not verified:
        return BackupResult(
            ok=False,
            directory=str(directory),
            bundle_path=str(bundle_path),
            error=f"git bundle verify failed: {verify_detail}",
        )

    shas = {info.name: info.sha for info in branches}
    restore = restore_command_for(repo_path, bundle_path)
    manifest_path = directory / MANIFEST_NAME
    manifest = {
        "repo": str(repo_path),
        "created_utc": _timestamp(now),
        "bundle": str(bundle_path),
        "branches": shas,
        "config": config_snapshot or {},
        "kept": keep_report or {},
        "restore_command": restore,
        "verify_output": verify_detail,
    }
    try:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
    except OSError as exc:
        return BackupResult(
            ok=False,
            directory=str(directory),
            bundle_path=str(bundle_path),
            error=f"cannot write manifest {manifest_path}: {exc}",
        )

    return BackupResult(
        ok=True,
        directory=str(directory),
        bundle_path=str(bundle_path),
        manifest_path=str(manifest_path),
        restore_command=restore,
        shas=shas,
    )


def sha_still_matches(repo: str | Path, name: str, expected: str) -> bool:
    """Re-read the branch's SHA; True only if it is still ``expected``.

    Step 5 of the contract. Between bundling and deleting, someone can
    push to a branch — and the bundle would then be one commit short of
    what the delete destroys. A branch that moved is dropped from the
    deletion set and reported as ``moved-during-pass``.
    """
    if not expected:
        return False
    current = branch_sha(repo, name)
    return current is not None and current == expected


# EOF
