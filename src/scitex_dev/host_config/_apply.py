#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_apply.py
"""Idempotent applier + audit trail for the ``scitex_dev.host_config`` federation.

Separated from ``scitex_dev.host_config`` (which stays pure: declare and
compare, never write) because everything here touches the filesystem as
root and therefore deserves its own tests and its own review.

THE THREE RULES, from the operator's 2026-08-12 ruling
------------------------------------------------------
1. *Idempotent.* A converged host reports ``unchanged`` for every spec
   and writes nothing -- and SAYS so, rather than printing nothing and
   leaving the reader unable to tell a no-op from a crash.
2. *Report what changed.* Every run appends to
   ``~/.scitex/dev/runtime/logs/host-config.log``. A job that silently
   converges is the same defect as a hook that silently no-ops: the
   record has to survive the run.
3. *Drift is visible, not quietly corrected.* A managed file that
   someone edited is reported and LEFT ALONE. Overwriting it needs an
   explicit ``--force``, and even then the old file is backed up first,
   so the evidence of what was there outlives the repair.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import (
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    HostConfigSpec,
    evaluate,
)

#: Append-only audit trail. Same directory the managed cron/timer jobs
#: already log to (see ``_ecosystem_jobs``), so an operator looking for
#: "what did the fleet do to this host" finds it in one place.
AUDIT_LOG = Path.home() / ".scitex" / "dev" / "runtime" / "logs" / "host-config.log"

#: Suffix for the copy taken before ``--force`` overwrites a drifted file.
BACKUP_SUFFIX = ".scitex-bak"


def backup_path_for(path: Path, *, now: datetime | None = None) -> Path:
    """Timestamped sibling used to preserve a file before overwriting it.

    UTC, second resolution, sortable: ``<path>.scitex-bak.20260812T075500Z``.
    A sibling rather than a central backup dir so the copy is impossible
    to miss when someone later inspects the drop-in directory.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return path.with_name(f"{path.name}{BACKUP_SUFFIX}.{stamp}")


def _write(target: Path, spec: HostConfigSpec) -> None:
    """Create parents, write the declared content, set the declared mode."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec.content, encoding="utf-8")
    os.chmod(target, int(spec.mode, 8))


def apply_specs(
    specs: list[HostConfigSpec],
    *,
    root: str = "/",
    force: bool = False,
    dry_run: bool = False,
    hostname: str | None = None,
    run_apply_commands: bool = True,
) -> list[dict]:
    """Converge ``specs`` on this host and return one record per spec.

    Each record is ``{name, path, state, action, detail}`` where
    ``action`` is one of:

    * ``unchanged``   -- already as declared (the idempotent no-op)
    * ``skipped``     -- ``not_applicable`` on this host
    * ``created``     -- the file was absent and has been written
    * ``drift``       -- differs, and was DELIBERATELY NOT touched
    * ``repaired``    -- differed and was overwritten under ``--force``
                         (the previous file is backed up; the backup
                         path is named in ``detail``)
    * ``would-*``     -- the ``dry_run`` preview of the above

    ``apply_command`` runs at most once per distinct command, and ONLY
    when something actually changed -- a periodic job must not restart
    a daemon on every pass just because a file is (still) correct.
    """
    records: list[dict] = []
    reload_commands: list[str] = []

    for spec in specs:
        status = evaluate(spec, root=root, hostname=hostname)
        target = Path(root) / spec.path.lstrip("/")

        if status.state == STATE_NOT_APPLICABLE:
            records.append(_rec(spec, status.state, "skipped", status.detail))
            continue

        if status.state == STATE_OK:
            records.append(_rec(spec, status.state, "unchanged", status.detail))
            continue

        if status.state == STATE_ABSENT:
            if dry_run:
                records.append(
                    _rec(spec, status.state, "would-create", f"would write {spec.path}")
                )
            else:
                _write(target, spec)
                records.append(
                    _rec(spec, status.state, "created", f"wrote {spec.path}")
                )
                _queue(reload_commands, spec.apply_command)
            continue

        # STATE_DRIFT -- the deliberate stop. Never converge silently.
        if not force:
            records.append(
                _rec(
                    spec,
                    STATE_DRIFT,
                    "drift",
                    f"{status.detail}; NOT overwritten (pass --force to repair, "
                    f"which backs the current file up first)",
                )
            )
            continue

        backup = backup_path_for(target)
        if dry_run:
            records.append(
                _rec(
                    spec,
                    STATE_DRIFT,
                    "would-repair",
                    f"would back up to {backup} then rewrite {spec.path}",
                )
            )
            continue

        shutil.copy2(target, backup)
        _write(target, spec)
        records.append(
            _rec(spec, STATE_DRIFT, "repaired", f"backed up to {backup}; rewrote")
        )
        _queue(reload_commands, spec.apply_command)

    if run_apply_commands and not dry_run:
        for command in reload_commands:
            rc = subprocess.run(command, shell=True).returncode
            records.append(
                {
                    "name": "(apply_command)",
                    "path": "-",
                    "state": "-",
                    "action": "reloaded" if rc == 0 else "reload-failed",
                    "detail": f"{command} -> exit {rc}",
                }
            )
    elif reload_commands:
        for command in reload_commands:
            records.append(
                {
                    "name": "(apply_command)",
                    "path": "-",
                    "state": "-",
                    "action": "would-reload",
                    "detail": command,
                }
            )

    return records


def _queue(commands: list[str], command: str | None) -> None:
    """Remember ``command`` once, preserving declaration order."""
    if command and command not in commands:
        commands.append(command)


def _rec(spec: HostConfigSpec, state: str, action: str, detail: str) -> dict:
    return {
        "name": spec.name,
        "path": spec.path,
        "state": state,
        "action": action,
        "detail": detail,
    }


def needs_root(records: list[dict], specs: list[HostConfigSpec]) -> bool:
    """Whether any pending change would require privileges we may lack."""
    by_name = {s.name: s for s in specs}
    return any(
        r["action"].startswith(("would-create", "would-repair"))
        and by_name[r["name"]].requires_root
        for r in records
        if r["name"] in by_name
    )


def write_audit(records: list[dict], *, mode: str, log_path: Path | None = None) -> Path:
    """Append this run to the audit log and return the log's path.

    Written even when nothing changed: "checked at T, all four specs
    already correct" is exactly the record that lets a future reader
    distinguish a converged host from a job that never ran.
    """
    path = log_path or AUDIT_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    host = os.uname().nodename
    lines = [f"{stamp} host={host} mode={mode} specs={len(records)}"]
    for rec in records:
        lines.append(
            f"{stamp} host={host}   {rec['action']:<14} {rec['name']}  {rec['detail']}"
        )
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


__all__ = [
    "AUDIT_LOG",
    "BACKUP_SUFFIX",
    "apply_specs",
    "backup_path_for",
    "needs_root",
    "write_audit",
]

# EOF
