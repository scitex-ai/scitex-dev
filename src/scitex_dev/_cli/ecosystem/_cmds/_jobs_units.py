#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verb bodies shared by the ``service`` and ``timer`` kind groups.

``service`` and ``timer`` are DIFFERENT KINDS with different applicable
fields (a service has ``restart_policy``/``watchdog_sec`` and no schedule;
a timer has a cadence and no restart policy), which is exactly why they get
separate CLI groups. What they share is the systemd ``--user`` unit
directory and the read/write mechanics over it, so those live here once
rather than being copy-pasted into two groups that then drift.

STDOUT IS THE PAYLOAD. Every diagnostic, refusal, deprecation note and
progress line goes to stderr; stdout carries only the answer, so
``--json`` output stays parseable with any warning path active. A sibling
measured a stale-registry ``WARN:`` reaching stdout and turning 7 tests red
across three unrelated PRs — this module does not repeat that.
"""

from __future__ import annotations

import json as _json
import subprocess
from pathlib import Path

import click

from ._jobs_supervision import (
    guard_existing_supervisors,
    probe_supervision,
    require_supervision,
    unit_dir,
)


def jobs_for(kind: str, name: str | None = None):
    """Discovered jobs of ``kind``, optionally narrowed to ``name``.

    Raises ``ClickException`` when ``name`` matches nothing — a filter that
    silently yields an empty list is how ``sac dev systemd list`` reported
    "No sac systemd-kind jobs." with exit 0 for weeks while four timers,
    including the fleet's sole OAuth refresher, were live.
    """
    from ....jobs import jobs_of_kind

    jobs = jobs_of_kind(kind)
    if name is None:
        return jobs
    narrowed = [j for j in jobs if j.name == name]
    if not narrowed:
        known = ", ".join(sorted(j.name for j in jobs)) or "(none discovered)"
        raise click.ClickException(
            f"no kind={kind!r} job named {name!r}. Discovered: {known}"
        )
    return narrowed


def emit_list(kind: str, as_json: bool) -> None:
    """``<kind> list`` — every discovered job of ``kind``."""
    jobs = jobs_for(kind)
    if as_json:
        click.echo(_json.dumps([job_dict(kind, j) for j in jobs]))
        return
    if not jobs:
        click.echo(f"No kind={kind} jobs discovered.")
        return
    for job in jobs:
        click.echo(f"  {job.name:34s} {_cadence_of(kind, job)}")
        click.echo(f"  {'':34s} {job.description}")


def job_dict(kind: str, job) -> dict:
    """The JSON shape for one job — only fields that APPLY to ``kind``.

    A ``service`` has no cadence and a ``timer`` has no restart policy; the
    model already forbids the inapplicable combinations, so emitting the
    fields anyway would invite a consumer to read a permanent ``null`` as
    meaningful.
    """
    common = {
        "name": job.name,
        "kind": job.kind,
        "command": job.command,
        "description": job.description,
        "source": job.name.split(".", 1)[0] if "." in job.name else "scitex-dev",
    }
    if kind == "service":
        common.update(
            {
                "on_boot_sec": job.on_boot_sec,
                "restart_policy": job.restart_policy,
                "watchdog_sec": job.watchdog_sec,
                "unit": f"{job.name}.service",
            }
        )
    else:
        common.update(
            {
                "on_boot_sec": job.on_boot_sec,
                "on_unit_active_sec": job.on_unit_active_sec,
                "schedule": job.schedule,
                "unit": f"{job.name}.timer",
            }
        )
    return common


def _cadence_of(kind: str, job) -> str:
    if kind == "service":
        return f"restart={job.restart_policy}"
    return "every " + (job.on_unit_active_sec or f"(derived from {job.schedule})")


def unit_suffixes(kind: str) -> tuple[str, ...]:
    """Which unit files a job of ``kind`` owns.

    A timer owns BOTH — the ``.timer`` that fires and the oneshot
    ``.service`` it triggers — so uninstall must remove both or the next
    install inherits a stale body.
    """
    return (".service",) if kind == "service" else (".service", ".timer")


def enable_target(kind: str, job) -> str:
    """The unit systemctl acts on: ``<name>.timer`` for timers."""
    return f"{job.name}.timer" if kind == "timer" else f"{job.name}.service"


def _unit_text(kind: str, job, suffix: str) -> str:
    from ....jobs import _systemd as sd

    if suffix == ".timer":
        return sd.build_timer_unit(job)
    return sd.build_service_unit(job)


def do_install(
    kind: str,
    *,
    name: str | None,
    dry_run: bool,
    yes: bool,
    adopt: bool,
    force: bool,
    home: Path | None = None,
) -> None:
    """``<kind> install`` — write unit files, refusing to double-supervise."""
    jobs = jobs_for(kind, name)
    if not jobs:
        click.echo(f"No kind={kind} jobs discovered.")
        return

    if dry_run:
        # A preview must work on a host that cannot install, or an operator
        # on a NAS cannot even SEE what the unit would say.
        for job in jobs:
            for suffix in unit_suffixes(kind):
                click.echo(f"# {job.name}{suffix}")
                click.echo(_unit_text(kind, job, suffix))
        return

    require_supervision(kind, "install", probe_supervision())

    if not yes:
        click.echo("Refusing to write unit files without --yes/-y.", err=True)
        raise SystemExit(2)

    target = unit_dir(home)
    written: list[str] = []
    for job in jobs:
        if not guard_existing_supervisors(job, adopt=adopt, force=force, home=home):
            continue
        target.mkdir(parents=True, exist_ok=True)
        for suffix in unit_suffixes(kind):
            path = target / f"{job.name}{suffix}"
            path.write_text(_unit_text(kind, job, suffix), encoding="utf-8")
            written.append(str(path))
            click.echo(f"wrote {path}")

    if not written:
        return
    click.echo("", err=True)
    click.echo("Enable with:", err=True)
    click.echo("  systemctl --user daemon-reload", err=True)
    for job in jobs:
        click.echo(
            f"  systemctl --user enable --now {enable_target(kind, job)}",
            err=True,
        )


def do_uninstall(
    kind: str,
    *,
    name: str | None,
    dry_run: bool,
    yes: bool,
    home: Path | None = None,
) -> None:
    """``<kind> uninstall`` — remove this kind's unit files."""
    jobs = jobs_for(kind, name)
    target = unit_dir(home)

    if dry_run:
        for job in jobs:
            for suffix in unit_suffixes(kind):
                path = target / f"{job.name}{suffix}"
                if path.exists():
                    click.echo(f"would remove {path}")
        return

    if not yes:
        click.echo("Refusing to remove unit files without --yes/-y.", err=True)
        raise SystemExit(2)

    removed = 0
    for job in jobs:
        for suffix in unit_suffixes(kind):
            path = target / f"{job.name}{suffix}"
            if path.exists():
                path.unlink()
                removed += 1
                click.echo(f"removed {path}")
    if removed == 0:
        click.echo("No unit files found to remove.")
    else:
        click.echo("", err=True)
        click.echo("Run: systemctl --user daemon-reload", err=True)


def do_status(kind: str, *, name: str, as_json: bool, home: Path | None = None) -> None:
    """``<kind> status NAME`` — installed? supervised? by what?

    READ-ONLY, and it works on a host with no systemd: "there is no unit
    and there never can be" is the most useful answer a NAS can give, and
    refusing to answer it would leave the operator with no way to ask.
    """
    from ._jobs_supervision import find_supervisors

    job = jobs_for(kind, name)[0]
    sup = probe_supervision()
    supervisors = find_supervisors(job, home=home)
    unit_paths = [
        str(unit_dir(home) / f"{job.name}{s}")
        for s in unit_suffixes(kind)
        if (unit_dir(home) / f"{job.name}{s}").exists()
    ]
    active = _systemctl_show(kind, job) if sup.available else None

    if as_json:
        click.echo(
            _json.dumps(
                {
                    "name": job.name,
                    "kind": job.kind,
                    "host_mechanism": sup.mechanism,
                    "host_supports_kind": sup.available,
                    "installed_units": unit_paths,
                    "active_state": active,
                    "supervisors": [
                        {
                            "mechanism": s.mechanism,
                            "locus": s.locus,
                            "scitex_dev_managed": s.ours,
                        }
                        for s in supervisors
                    ],
                }
            )
        )
        return

    click.echo(f"{job.name}  (kind={job.kind})")
    click.echo(f"  host mechanism : {sup.mechanism}")
    click.echo(f"  units installed: {', '.join(unit_paths) or '(none)'}")
    click.echo(f"  active state   : {active or '(unknown — no user manager)'}")
    if not supervisors:
        click.echo("  supervisors    : (none)")
        return
    click.echo(f"  supervisors    : {len(supervisors)}")
    for s in supervisors:
        click.echo(f"    {s.describe()}")


def _systemctl_show(kind: str, job) -> str | None:
    """``systemctl --user is-active <unit>`` — ``None`` when unaskable."""
    try:
        proc = subprocess.run(
            ["systemctl", "--user", "is-active", enable_target(kind, job)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout or "").strip() or None


def do_systemctl(
    kind: str,
    verb: str,
    name: str,
    *,
    dry_run: bool = False,
    yes: bool = False,
    extra: tuple[str, ...] = (),
) -> None:
    """Run one ``systemctl --user <verb> <unit>``, refusing where impossible.

    ``dry_run`` / ``yes`` are the CLI-doctrine §2 pair every MUTATING verb
    carries, and they earn their place here rather than being ceremony:
    ``restart sac.listen`` bounces a live supervised daemon, and ``disable
    sac.accounts-refresh`` stops the fleet's sole OAuth refresher. Neither
    should happen because a name was typed one word off.

    Order of the three guards is deliberate:

    1. ``dry_run`` FIRST — a preview must work on a host that cannot run
       the verb at all, or an operator on a NAS cannot even see what the
       command would be.
    2. host capability — exits :data:`EXIT_UNSUPPORTED_HOST` with a named
       reason, so "impossible here" never reads as a transient failure.
    3. ``yes`` — the confirmation, refused with exit 2 like every other
       mutating verb in this repo.

    ``extra`` carries flags that belong to the verb rather than the unit
    (``--now`` for ``enable``/``disable``), keeping the argv assembly in
    one place instead of two near-identical copies per kind group.
    """
    job = jobs_for(kind, name)[0]
    unit = enable_target(kind, job)
    argv = ["systemctl", "--user", verb, *extra, unit]

    if dry_run:
        click.echo(" ".join(argv))
        return

    require_supervision(kind, verb, probe_supervision())

    if not yes:
        click.echo(
            f"Refusing to {verb} {unit} without --yes/-y (preview it with --dry-run).",
            err=True,
        )
        raise SystemExit(2)

    click.echo(f"$ {' '.join(argv)}", err=True)
    try:
        proc = subprocess.run(argv, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise click.ClickException(f"{' '.join(argv)}: {exc}") from exc
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    click.echo(f"{verb} {unit}: ok")


__all__ = [
    "do_install",
    "do_status",
    "do_systemctl",
    "do_uninstall",
    "emit_list",
    "enable_target",
    "job_dict",
    "jobs_for",
    "unit_suffixes",
]


# EOF
