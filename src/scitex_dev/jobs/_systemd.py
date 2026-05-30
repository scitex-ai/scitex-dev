#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure builders for systemd user ``.service`` / ``.timer`` unit files.

Format mirrors scitex-agent-container's
``scripts/systemd/sac-accounts-refresh.{service,timer}`` reference:
``Type=oneshot``, journal logging, ``Persistent=true`` timer, a boot
catch-up via ``OnBootSec``, and a recurring ``OnUnitActiveSec`` cadence.

The functions here are pure (string in, string out) so they are trivial
to unit-test; the CLI layer (``_cli/ecosystem/_cmds/_jobs_systemd``)
handles filesystem writes under ``~/.config/systemd/user/``.
"""

from __future__ import annotations

from .. import jobs as _jobs

DEFAULT_ON_BOOT_SEC = "15min"
DEFAULT_ON_UNIT_ACTIVE_SEC = "1h"

# Documentation URL stamped into generated units (operator breadcrumb).
_DOC_URL = "https://github.com/ywatanabe1989/scitex-dev"


def derive_on_unit_active_sec(schedule: str) -> str:
    """Derive an ``OnUnitActiveSec`` from a 5-field cron ``schedule``.

    Best-effort: this is only used when a job declares no explicit
    ``on_unit_active_sec``. We read the minute and hour fields and map a
    handful of common ``*/N`` step forms to a duration; anything we
    don't recognise falls back to ``DEFAULT_ON_UNIT_ACTIVE_SEC``.
    """
    fields = schedule.split()
    if len(fields) != 5:
        return DEFAULT_ON_UNIT_ACTIVE_SEC
    minute, hour = fields[0], fields[1]

    # "*/N * * * *"  -> every N minutes
    if minute.startswith("*/") and hour == "*":
        n = _safe_int(minute[2:])
        if n:
            return f"{n}min"
    # "M */N * * *"  -> every N hours
    if hour.startswith("*/"):
        n = _safe_int(hour[2:])
        if n:
            return f"{n}h"
    # "M H * * *"    -> a fixed daily time
    if minute.isdigit() and hour.isdigit():
        return "1d"
    return DEFAULT_ON_UNIT_ACTIVE_SEC


def _safe_int(text: str) -> int | None:
    try:
        return int(text)
    except ValueError:
        return None


def build_service_unit(job: _jobs.JobSpec) -> str:
    """Return the ``.service`` unit text for ``job`` (Type=oneshot)."""
    lines = [
        "[Unit]",
        f"Description={job.description or job.name}",
        f"Documentation={_DOC_URL}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        f"ExecStart=/usr/bin/env {job.command}",
        "StandardOutput=journal",
        "StandardError=journal",
        "RemainAfterExit=no",
    ]
    if job.timeout_sec is not None:
        lines.append(f"TimeoutStartSec={job.timeout_sec}s")
    lines.append("")
    return "\n".join(lines)


def build_timer_unit(job: _jobs.JobSpec) -> str:
    """Return the ``.timer`` unit text for ``job`` (Persistent=true)."""
    on_boot = job.on_boot_sec or DEFAULT_ON_BOOT_SEC
    on_active = job.on_unit_active_sec or derive_on_unit_active_sec(job.schedule)
    lines = [
        "[Unit]",
        f"Description=Timer for {job.name}",
        f"Documentation={_DOC_URL}",
        "",
        "[Timer]",
        f"OnBootSec={on_boot}",
        f"OnUnitActiveSec={on_active}",
        "Persistent=true",
        f"Unit={job.name}.service",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ]
    return "\n".join(lines)


# EOF
