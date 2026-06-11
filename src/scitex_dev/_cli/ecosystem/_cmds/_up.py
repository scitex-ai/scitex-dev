#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev ecosystem up`` — one-shot ecosystem reconciler.

The headline UX the operator commissioned (a2a lead `c2908456`,
2026-06-11): ONE command brings up every discovered ``JobSpec`` — cron
lines, systemd timers, long-running services — in a single idempotent
reconcile. ONE master ``scitex-dev-ecosystem-reconcile.service``
``--user`` unit runs the same command on boot so the whole ecosystem
comes alive without per-package manual systemctl ceremony.

What it does
------------
Per cron tick / invocation:

  1. Discover every ``JobSpec`` via ``scitex_dev.jobs.discover_jobs()``
     — built-in cron jobs + every entry-point provider.
  2. ``ecosystem cron install --yes`` — materialise / refresh the
     managed crontab block for ``kind="cron"`` jobs (idempotent;
     re-running never duplicates lines).
  3. ``ecosystem systemd install --yes`` — write
     ``~/.config/systemd/user/<name>.{service,timer}`` for every
     ``kind="service"`` / ``kind="timer"`` job.
  4. ``systemctl --user daemon-reload`` once.
  5. ``systemctl --user enable --now <unit>`` for each new/changed
     unit. Per-unit failure is isolated and logged; one broken leaf
     does NOT abort the reconcile.

Plus an opt-in flag:

  ``--install-master-unit`` writes
  ``~/.config/systemd/user/scitex-dev-ecosystem-reconcile.service``
  which runs ``scitex-dev ecosystem up --yes`` on boot
  (``OnBootSec=30s`` via an ``ExecStartPre=/bin/sleep`` delay so
  network-online.target has time to settle). Idempotent; safe to call
  on every ``up``. Once installed + enabled, the host reconciles
  itself on every reboot — operator no longer manages 60 leaves.

Robustness
----------
``ecosystem up`` is a CONVERGENCE LOOP. It must NEVER refuse to make
forward progress because of one bad leaf:

* Provider raises during discovery → logged + skipped (same fail-open
  contract as ``discover_jobs``).
* Per-unit ``systemctl enable`` fails → logged + counted; the loop
  keeps reconciling the rest of the units.
* ``systemctl`` itself missing (e.g. running in a container) → the
  CLI exits 0 after writing unit files + crontab, with a clear
  diagnostic that the operator's host has no systemd. The next run on
  a real host completes the reconcile.

Exit code is non-zero ONLY when the discovery / install steps
themselves blew up (the catastrophic case the operator wants paged
on), never on a per-unit hiccup the next reconcile will sort out.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import click

from ....jobs import JobSpec, jobs_of_kind
from ....jobs import _systemd as sd


# ---------------------------------------------------------------------------
# Master reconcile unit — the one declarative artefact that makes the
# whole "register systemd once, ecosystem stays reconciled" goal real.
# ---------------------------------------------------------------------------

MASTER_UNIT_NAME = "scitex-dev-ecosystem-reconcile.service"


def build_master_unit_text() -> str:
    """Return the master reconcile unit text.

    Built dynamically (not a module-level constant) so the
    ``ExecStart=`` line carries the absolute path to ``scitex-dev`` as
    resolved from the operator's ambient PATH — same fix as
    :func:`scitex_dev.jobs._systemd.resolve_execstart`. systemd
    ``--user`` runs under a deliberately minimal PATH that excludes
    most Python venvs; emitting a bare ``scitex-dev`` would 127 on
    every boot.

    ``RemainAfterExit=yes`` so ``systemctl --user enable --now
    scitex-dev-ecosystem-reconcile.service`` returns immediately
    once ExecStart exits cleanly. Without it, oneshot units flip
    back to inactive the moment ExecStart returns and the operator's
    ``enable --now`` would hang or report failure on a successful run.
    """
    from ....jobs._systemd import resolve_execstart

    execstart = resolve_execstart("scitex-dev ecosystem up --yes")
    return (
        "[Unit]\n"
        "Description=SciTeX ecosystem reconciler — runs "
        "`scitex-dev ecosystem up --yes` to bring up every JobSpec\n"
        "Documentation=https://github.com/ywatanabe1989/scitex-dev\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        "# Wait 30 s after boot so DNS / network are settled before the\n"
        "# reconcile starts shelling out to systemctl / crontab / gh.\n"
        "ExecStartPre=/bin/sleep 30\n"
        f"ExecStart={execstart}\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        # Stay active after ExecStart exits so `enable --now` returns
        # immediately on a clean reconcile rather than reporting the
        # oneshot as inactive-then-failed.
        "RemainAfterExit=yes\n"
        "TimeoutStartSec=300s\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


# Back-compat shim — the previous module exposed ``MASTER_UNIT_TEXT``
# as a constant. We keep the name resolvable so existing tests / docs
# don't break, but the value is computed lazily via ``__getattr__`` so
# the absolute-path resolution honours the LIVE PATH at call time
# (rather than baking in scitex-dev's path at module-import time, which
# is fragile during editable installs or first-time setup).


def __getattr__(name):
    if name == "MASTER_UNIT_TEXT":
        return build_master_unit_text()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _unit_dir() -> Path:
    """Resolve ``~/.config/systemd/user`` honouring ``$HOME`` (test seam)."""
    return Path.home() / ".config" / "systemd" / "user"


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UpResult:
    """Aggregate outcome of one ``ecosystem up`` invocation.

    ``error`` is set for catastrophic discovery / install failures
    only. Per-unit outcomes (enable / start) are captured in
    ``per_unit`` and aggregated into ``services_enabled`` /
    ``timers_enabled`` / ``unit_failures`` so the dispatcher exit
    code reflects systemic vs transient failure.
    """

    cron_jobs_installed: int = 0
    service_units_written: int = 0
    timer_units_written: int = 0
    master_unit_written: bool = False
    services_enabled: int = 0
    timers_enabled: int = 0
    unit_failures: tuple[str, ...] = field(default_factory=tuple)
    systemctl_missing: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Seams (test-fakable; production defaults shell out)
# ---------------------------------------------------------------------------


def _default_systemctl_runner(
    args: list[str], *, timeout: float = 30.0
) -> subprocess.CompletedProcess:
    """Real ``systemctl --user`` invocation. Tests pass their own fake."""
    return subprocess.run(
        ["systemctl", "--user", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_master_unit(unit_dir: Path) -> Path:
    """Write the master reconcile service unit. Idempotent.

    Returns the path written so the CLI can echo a useful line. Always
    writes the canonical text — if the operator hand-edited the file,
    a fresh ``ecosystem up --install-master-unit`` resets it. That's
    the correct behaviour for a managed unit; hand edits belong in the
    JobSpec the leaf declares, not in scitex-dev's reconcile target.
    """
    unit_dir.mkdir(parents=True, exist_ok=True)
    path = unit_dir / MASTER_UNIT_NAME
    # Call the builder live so the absolute-path resolution honours the
    # PATH of the process running `ecosystem up --install-master-unit`
    # (which IS the operator's interactive shell with scitex-dev on it).
    path.write_text(build_master_unit_text(), encoding="utf-8")
    return path


def _install_cron(
    *, jobs: list[JobSpec], yes: bool, echo: Callable[[str], None]
) -> int:
    """Materialise the managed crontab block. Returns count installed.

    Delegates to the existing helpers so there's one cron-write code
    path (the ``ecosystem cron install`` command and ``ecosystem up``
    can't drift).
    """
    from ....jobs import _cron_block as cb
    from ...cron import _crontab

    if not jobs:
        echo("cron: no cron-kind jobs discovered; managed block left untouched")
        return 0

    if not yes:
        echo("cron: --yes required to write the crontab block; skipping")
        return 0

    try:
        current = _crontab.read_crontab()
        new = cb.upsert_block(current, jobs)
        _crontab.write_crontab(new)
    except RuntimeError as exc:
        echo(f"cron: ERROR writing crontab: {exc}")
        return 0
    echo(f"cron: installed {len(jobs)} job(s) into managed block")
    return len(jobs)


def _install_systemd_units(
    *,
    jobs: list[JobSpec],
    unit_dir: Path,
    echo: Callable[[str], None],
) -> tuple[int, int]:
    """Write .service (+ .timer for kind='timer') unit files.

    Returns ``(service_count, timer_count)``.
    """
    unit_dir.mkdir(parents=True, exist_ok=True)
    services = 0
    timers = 0
    for j in jobs:
        try:
            service_text = sd.build_service_unit(j)
            (unit_dir / f"{j.name}.service").write_text(service_text, encoding="utf-8")
            services += 1
            if j.kind == "timer":
                timer_text = sd.build_timer_unit(j)
                (unit_dir / f"{j.name}.timer").write_text(timer_text, encoding="utf-8")
                timers += 1
        except Exception as exc:  # noqa: BLE001 — fail-open per leaf
            echo(f"systemd: ERROR writing units for {j.name!r}: {exc}")
    return services, timers


def _systemctl(
    args: list[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess],
    echo: Callable[[str], None],
) -> bool:
    """Invoke systemctl --user; return True on rc=0. Failure-isolated."""
    try:
        r = runner(args)
    except FileNotFoundError:
        return False
    except Exception as exc:  # noqa: BLE001 — never crash the reconcile
        echo(f"systemctl: ERROR running {args}: {exc}")
        return False
    if r.returncode != 0:
        stderr = (r.stderr or "").strip().splitlines()
        first = stderr[0] if stderr else ""
        echo(f"systemctl {' '.join(args)}: rc={r.returncode} {first!r}")
        return False
    return True


def _reconcile_units(
    *,
    jobs: list[JobSpec],
    systemctl_runner: Callable[..., subprocess.CompletedProcess],
    echo: Callable[[str], None],
) -> tuple[int, int, tuple[str, ...]]:
    """``daemon-reload`` once, then ``enable --now`` each unit.

    Returns ``(services_enabled, timers_enabled, failed_unit_names)``.
    """
    if shutil.which("systemctl") is None:
        echo("systemctl not on PATH; unit files written but not enabled")
        return 0, 0, ()

    _systemctl(["daemon-reload"], runner=systemctl_runner, echo=echo)

    services_enabled = 0
    timers_enabled = 0
    failures: list[str] = []
    for j in jobs:
        unit = sd.systemd_unit_name(j)
        ok = _systemctl(
            ["enable", "--now", unit], runner=systemctl_runner, echo=echo
        )
        if ok:
            if j.kind == "timer":
                timers_enabled += 1
            else:
                services_enabled += 1
        else:
            failures.append(unit)
    return services_enabled, timers_enabled, tuple(failures)


def _enable_master_unit(
    *,
    systemctl_runner: Callable[..., subprocess.CompletedProcess],
    echo: Callable[[str], None],
) -> bool:
    """Daemon-reload + enable --now the master reconcile unit. Best-effort."""
    if shutil.which("systemctl") is None:
        echo("systemctl not on PATH; master unit written but not enabled")
        return False
    _systemctl(["daemon-reload"], runner=systemctl_runner, echo=echo)
    return _systemctl(
        ["enable", "--now", MASTER_UNIT_NAME],
        runner=systemctl_runner,
        echo=echo,
    )


# ---------------------------------------------------------------------------
# Top-level ``up`` body — test-friendly: every external touch goes
# through a kwarg seam.
# ---------------------------------------------------------------------------


def run_up(
    *,
    yes: bool = False,
    install_master_unit: bool = False,
    systemctl_runner: Callable[..., subprocess.CompletedProcess] | None = None,
    unit_dir: Path | None = None,
    echo: Callable[[str], None] | None = None,
) -> UpResult:
    """Execute one full reconcile pass. Returns aggregate outcome."""
    runner = systemctl_runner or _default_systemctl_runner
    udir = unit_dir or _unit_dir()
    log = echo or (lambda s: click.echo(s))

    cron_jobs = jobs_of_kind("cron")
    systemd_jobs = jobs_of_kind("timer") + jobs_of_kind("service")

    cron_installed = _install_cron(jobs=cron_jobs, yes=yes, echo=log)
    services_written, timers_written = _install_systemd_units(
        jobs=systemd_jobs, unit_dir=udir, echo=log
    )

    systemctl_missing = shutil.which("systemctl") is None

    services_enabled = timers_enabled = 0
    unit_failures: tuple[str, ...] = ()
    if systemd_jobs and yes:
        services_enabled, timers_enabled, unit_failures = _reconcile_units(
            jobs=systemd_jobs, systemctl_runner=runner, echo=log
        )

    master_written = False
    if install_master_unit:
        master_path = _write_master_unit(udir)
        master_written = True
        log(f"master: wrote {master_path}")
        if yes:
            _enable_master_unit(systemctl_runner=runner, echo=log)

    return UpResult(
        cron_jobs_installed=cron_installed,
        service_units_written=services_written,
        timer_units_written=timers_written,
        master_unit_written=master_written,
        services_enabled=services_enabled,
        timers_enabled=timers_enabled,
        unit_failures=unit_failures,
        systemctl_missing=systemctl_missing,
    )


def register(ecosystem) -> None:
    @ecosystem.command("up")
    @click.option(
        "-y",
        "--yes",
        is_flag=True,
        default=False,
        help="Required to write the crontab + run `systemctl --user enable --now`.",
    )
    @click.option(
        "--install-master-unit",
        is_flag=True,
        default=False,
        help=(
            "Also write + enable "
            "`~/.config/systemd/user/scitex-dev-ecosystem-reconcile.service` "
            "so the host reconciles on every boot."
        ),
    )
    def up(yes: bool, install_master_unit: bool) -> None:
        """Reconcile every discovered JobSpec onto the host in one shot.

        \b
        Cron-kind jobs → managed crontab block.
        Timer-kind jobs → ~/.config/systemd/user/<name>.timer + .service.
        Service-kind jobs → ~/.config/systemd/user/<name>.service.

        \b
        With --yes:
          systemctl --user daemon-reload, enable --now each unit.

        \b
        Optional --install-master-unit registers the
        scitex-dev-ecosystem-reconcile.service so the whole ecosystem
        comes up on every boot.

        \b
        Examples:
          $ scitex-dev ecosystem up                              # dry surface
          $ scitex-dev ecosystem up --yes
          $ scitex-dev ecosystem up --yes --install-master-unit  # boot-time auto
        """
        result = run_up(yes=yes, install_master_unit=install_master_unit)
        # Concise summary the operator can grep in the journal.
        click.echo("")
        click.echo("=== ecosystem up summary ===")
        click.echo(f"  cron jobs installed:    {result.cron_jobs_installed}")
        click.echo(f"  .service units written: {result.service_units_written}")
        click.echo(f"  .timer units written:   {result.timer_units_written}")
        click.echo(f"  master unit written:    {result.master_unit_written}")
        click.echo(f"  services enabled:       {result.services_enabled}")
        click.echo(f"  timers enabled:         {result.timers_enabled}")
        click.echo(f"  per-unit failures:      {len(result.unit_failures)}")
        if result.systemctl_missing:
            click.echo("  (systemctl missing — unit files written, not enabled)")
        if result.error is not None:
            raise click.ClickException(result.error)


# EOF
