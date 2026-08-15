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
    STATE_PRECONDITION_UNMET,
    HostConfigSpec,
    evaluate,
)

#: Append-only audit trail. Same directory the managed cron/timer jobs
#: already log to (see ``_ecosystem_jobs``), so an operator looking for
#: "what did the fleet do to this host" finds it in one place.
AUDIT_LOG = Path.home() / ".scitex" / "dev" / "runtime" / "logs" / "host-config.log"

#: Env override for :func:`audit_log_path`. Operationally useful (a host whose
#: home is read-only can still keep a trail) and it is what makes the failure
#: mode TESTABLE with real bytes instead of a patched internal.
AUDIT_LOG_ENV = "SCITEX_DEV_HOST_CONFIG_LOG"


def audit_log_path() -> Path:
    """Resolve the audit log AT CALL TIME, honouring :data:`AUDIT_LOG_ENV`.

    ``AUDIT_LOG`` is computed at IMPORT time, which quietly made this path
    unconfigurable and untestable: nothing a caller or a test does after the
    module loads can move it. That is why the only way to exercise an
    unwritable log was to patch a production internal — and a test that
    rewrites production internals is not testing production.
    """
    override = os.environ.get(AUDIT_LOG_ENV)
    return Path(override) if override else AUDIT_LOG

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
    * ``blocked``     -- ``requires_command`` is missing, so the file
                         would be read by nothing; NOT written, not
                         even under ``--force``
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

        if status.state == STATE_PRECONDITION_UNMET:
            # Deliberately NOT written, even under --force. Writing it
            # would create a file that looks right, is read by nothing,
            # and reports `ok` on every subsequent check -- a guard that
            # cannot detect what it was installed for while claiming it
            # can. `blocked` keeps it visible until the precondition is
            # actually satisfied.
            records.append(_rec(spec, status.state, "blocked", status.detail))
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


def observe_specs(
    specs: list[HostConfigSpec],
    *,
    root: str = "/",
    hostname: str | None = None,
    timeout_sec: int = 30,
) -> list[dict]:
    """Run each spec's ``verify_command`` and return what the host SAID.

    THESE ARE NOT COMPLIANCE VERDICTS, and keeping the two apart is the
    whole reason this is a separate function rather than another branch
    inside :func:`apply_specs`.

    ``ok`` / ``absent`` / ``drift`` answer ONE question: does the file on
    disk match the declaration? That is a statement about configuration,
    and it is fully decidable. ``verify_command`` answers a different
    one: did the configuration actually take effect in the running
    system? Those can legitimately disagree forever. A host that
    REQUESTS an address via DHCP Option 50 and is granted a different
    one has a perfectly correct config file -- ``ok`` -- and an
    interface that does not match it. Reporting that as ``drift`` would
    accuse the configuration of a fault it does not have, and would
    train everyone to ignore drift.

    So an observation carries ``action="observed"``, its own exit code,
    and the command's output. It never changes a verdict and never
    enters the pending count. The caller decides what the difference
    means; a fleet-wide reconciler can store it as ACTUAL state beside
    the DESIRED state the declaration holds.

    A spec with no ``verify_command`` yields nothing -- silence here
    means "this declaration offers no observation", which is why the
    field's absence is worth noticing when reviewing a new spec.
    """
    records: list[dict] = []
    for spec in specs:
        if not spec.verify_command:
            continue
        status = evaluate(spec, root=root, hostname=hostname)
        if status.state in (STATE_NOT_APPLICABLE, STATE_PRECONDITION_UNMET):
            # Running `auditctl -l` on a host with no auditd produces a
            # shell error that reads like a finding. Skip it: the
            # precondition record already says the real thing.
            continue
        if spec.verify_requires_root and _euid() != 0:
            # Same reasoning, different cause. `auditctl -l` needs
            # CAP_AUDIT_CONTROL; run as a normal user it returns a
            # permission error, and a permission error sitting in an
            # observation column is indistinguishable at a glance from
            # the audit rules having gone missing. Say plainly that the
            # observation was NOT taken -- an unmeasured fact must not
            # be dressed up as a measured one.
            records.append(
                {
                    "name": spec.name,
                    "path": spec.path,
                    "state": "observation",
                    "action": "not-observed",
                    "detail": (
                        f"`{spec.verify_command}` needs root; this check "
                        f"runs unprivileged by design. Re-run as root to "
                        f"observe."
                    ),
                    "exit_code": None,
                    "output": "",
                }
            )
            continue
        try:
            proc = subprocess.run(
                spec.verify_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            output = (proc.stdout or proc.stderr or "").strip()
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            output = f"timed out after {timeout_sec}s"
            rc = None
        records.append(
            {
                "name": spec.name,
                "path": spec.path,
                "state": "observation",
                "action": "observed",
                "detail": f"$ {spec.verify_command} -> exit {rc}",
                "exit_code": rc,
                "output": output,
            }
        )
    return records


def _euid() -> int:
    """Effective uid, or 0 where the platform has no concept of one."""
    return os.geteuid() if hasattr(os, "geteuid") else 0


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
    path = log_path or audit_log_path()
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
    "observe_specs",
    "backup_path_for",
    "needs_root",
    "write_audit",
]

# EOF
