#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure builders for systemd user ``.service`` / ``.timer`` unit files.

Two shapes, selected by ``JobSpec.kind``:

* ``kind="timer"`` — oneshot ``.service`` + persistent ``.timer``.
  Format mirrors scitex-agent-container's
  ``scripts/systemd/sac-accounts-refresh.{service,timer}`` reference:
  ``Type=oneshot``, journal logging, ``Persistent=true`` timer, a boot
  catch-up via ``OnBootSec``, and a recurring ``OnUnitActiveSec``
  cadence.

* ``kind="service"`` — long-running ``.service`` only (no timer).
  ``Type=simple`` + ``Restart=<policy>``. Used by long-running
  user-space units (the 8051 scitex-todo dashboard, a long-poll
  listener, etc.). ``OnBootSec`` becomes a startup delay implemented
  via ``ExecStartPre=/bin/sleep <N>`` (timers are the only systemd
  mechanism that expose ``OnBootSec`` directly).

The functions here are pure (JobSpec in, string out) so they are
trivial to unit-test; the CLI layer
(``_cli/ecosystem/_cmds/_jobs_systemd``) handles filesystem writes
under ``~/.config/systemd/user/``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .. import jobs as _jobs

from ._resolve import (  # noqa: F401 - re-exported for existing callers
    DEFAULT_ON_BOOT_SEC,
    DEFAULT_ON_UNIT_ACTIVE_SEC,
    _interpreter_bindir,
    _on_boot_sec_to_seconds,
    _safe_int,
    derive_on_unit_active_sec,
    resolve_execstart,
)

# Documentation URL stamped into generated units (operator breadcrumb).
_DOC_URL = "https://github.com/scitex-ai/scitex-dev"

_logger = logging.getLogger(__name__)


def build_service_unit(job: _jobs.JobSpec) -> str:
    """Return the ``.service`` unit text for ``job``.

    Branches on ``job.kind``:

    * ``"timer"`` → oneshot service triggered by the sibling ``.timer``.
    * ``"service"`` → long-running ``Type=simple`` with ``Restart=``
      from ``job.restart_policy``. ``on_boot_sec`` (if set) becomes an
      ``ExecStartPre=/bin/sleep <N>`` startup delay so the unit comes
      up gracefully N seconds after boot — the systemd Service idiom
      for "wait before starting" (Timers own ``OnBootSec`` directly;
      Services don't).
    """
    if job.kind == "service":
        return _build_long_running_service_unit(job)
    return _build_oneshot_service_unit(job)


def _build_oneshot_service_unit(job: _jobs.JobSpec) -> str:
    """Oneshot ``.service`` for ``kind="timer"`` jobs."""
    lines = [
        "[Unit]",
        f"Description={job.description or job.name}",
        f"Documentation={_DOC_URL}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=oneshot",
        f"ExecStart={resolve_execstart(job.command, venv=job.venv)}",
        "StandardOutput=journal",
        "StandardError=journal",
        _remain_after_exit_line(job),
    ]
    lines.extend(_environment_lines(job))
    if job.timeout_sec is not None:
        lines.append(f"TimeoutStartSec={job.timeout_sec}s")
    lines.append("")
    return "\n".join(lines)


def _remain_after_exit_line(job: _jobs.JobSpec) -> str:
    """``RemainAfterExit=`` — historically hardcoded to ``no``.

    A unit whose EFFECT outlives its process (a mount, a one-time setup
    step) needs ``yes``, or ``systemctl is-active`` reports ``inactive``
    the instant it succeeds. Unset still renders ``no``, so existing
    units stay byte-identical.
    """
    if job.remain_after_exit is None:
        return "RemainAfterExit=no"
    return f"RemainAfterExit={'yes' if job.remain_after_exit else 'no'}"


def _environment_lines(job: _jobs.JobSpec) -> list[str]:
    """``WorkingDirectory=`` / ``Environment=`` / ``EnvironmentFile=``.

    Shared by both unit builders, because a daemon and a timer body need
    the same three answers and had the same two gaps.

    Historically these could ONLY be derived from ``venv``, which made a
    hand-written unit unadoptable whenever it disagreed. An
    ``EnvironmentFile=`` is frequently the only on-disk record of where a
    daemon's configuration comes from, so dropping it does not lose a
    line — it starts the daemon with an empty environment while the unit
    still reports ``active``.

    Order matters: the venv-derived ``VIRTUAL_ENV=`` is emitted first and
    explicit entries follow, because systemd takes the LAST assignment of
    a repeated key, so a leaf that means to override it can.
    """
    lines: list[str] = []
    # An explicit directory WINS over the venv-derived one: a unit naming
    # its own directory is stating a requirement, not a preference.
    working_directory = job.working_directory
    if working_directory is None and job.venv:
        working_directory = str(Path(job.venv).parent)
    if working_directory:
        lines.append(f"WorkingDirectory={working_directory}")
    if job.venv:
        lines.append(f"Environment=VIRTUAL_ENV={job.venv}")
    if job.environment_file:
        lines.append(f"EnvironmentFile={job.environment_file}")
    lines.extend(f"Environment={entry}" for entry in job.environment)
    return lines


def _build_long_running_service_unit(job: _jobs.JobSpec) -> str:
    """Long-running ``.service`` for ``kind="service"`` jobs.

    ``Restart=<policy>`` keeps the unit alive per the leaf's declared
    policy. An ``ExecStartPre=/bin/sleep <N>`` step implements
    ``on_boot_sec`` (systemd Services don't natively expose
    ``OnBootSec`` — that's a Timer-only knob — so we materialise the
    delay as a pre-exec sleep).

    Watchdog (opt-in). ``Restart=`` handles a *crash* (the process
    exits) but is blind to a *hang* (the process is alive but wedged).
    ``WatchdogSec`` closes that gap — BUT it does nothing unless the
    daemon calls ``sd_notify(WATCHDOG=1)`` on a cadence faster than the
    interval, under ``Type=notify``. If we emitted ``WatchdogSec`` for a
    plain ``Type=simple`` daemon that never pings, systemd would decide
    the daemon "timed out" every interval and kill+restart it forever —
    a restart-storm footgun strictly worse than no watchdog at all.

    Therefore the watchdog is emitted ONLY when the JobSpec explicitly
    sets ``watchdog_sec`` (the leaf is declaring "I send WATCHDOG=1
    pings"). In that case we switch the unit to ``Type=notify`` and add
    ``WatchdogSec=<N>s``. Otherwise the unit stays ``Type=simple`` and
    relies on ``Restart=`` alone.
    """
    use_watchdog = job.watchdog_sec is not None
    lines = [
        "[Unit]",
        f"Description={job.description or job.name}",
        f"Documentation={_DOC_URL}",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        # An explicitly declared Type= wins: the leaf knows its own
        # startup contract, and a unit that says Type=exec means it.
        # Otherwise fall back to the historical choice — Type=notify ONLY
        # when a watchdog is requested, because a Type=notify unit whose
        # ExecStart never calls sd_notify(READY=1) would sit in
        # "activating" until TimeoutStartSec and fail. (The contradictory
        # pair — a watchdog with a non-notify type — is refused in
        # JobSpec.validate, not silently reconciled here.)
        f"Type={job.service_type}"
        if job.service_type
        else ("Type=notify" if use_watchdog else "Type=simple"),
    ]
    if job.on_boot_sec:
        seconds = _on_boot_sec_to_seconds(job.on_boot_sec)
        if seconds > 0:
            lines.append(f"ExecStartPre=/bin/sleep {seconds}")
    lines.extend(_environment_lines(job))
    if job.remain_after_exit is not None:
        # Absent for a long-running service historically, so this stays
        # fully omitted unless the leaf asks for it.
        lines.append(_remain_after_exit_line(job))
    lines.extend(
        [
            f"ExecStart={resolve_execstart(job.command, venv=job.venv)}",
            "StandardOutput=journal",
            "StandardError=journal",
            f"Restart={job.restart_policy}",
        ]
    )
    if use_watchdog:
        # Guards hangs. The leaf MUST ping sd_notify(WATCHDOG=1) faster
        # than this or systemd will treat the daemon as hung and restart
        # it — see the opt-in caveat in the docstring above.
        lines.append(f"WatchdogSec={job.watchdog_sec}s")
    if job.restart_policy != "no":
        # Sensible default the operator can override at the systemctl
        # level. Keeps a runaway restart loop from melting CPU on a
        # broken leaf.
        lines.append("RestartSec=5s")
    if job.restart_prevent_exit_status:
        # A process that says "do not retry" must be believed.
        #
        # MEASURED 2026-08-17 on compute-02: `gh-runner.service` printed
        # "Runner listener exit with terminated error, stop the service, no
        # retry needed", exited, and systemd restarted it — 32,071 times over
        # two days, ~1.5s CPU each, while reporting ActiveState=active. The
        # unit had `Restart=` and no exit-status exclusion, so an explicit
        # do-not-retry contract had nowhere to be expressed.
        #
        # A GENERATED unit that cannot express it would loop identically, so
        # this is a prerequisite for adopting any hand-written unit that
        # already has it — not a nicety.
        lines.append(f"RestartPreventExitStatus={job.restart_prevent_exit_status}")
    if job.timeout_sec is not None:
        lines.append(f"TimeoutStartSec={job.timeout_sec}s")

    # STOP SEMANTICS. Omitting these is not a cosmetic loss: systemd's default
    # stop is SIGTERM then SIGKILL at 90s, so a daemon that wants SIGINT gets
    # a hard kill and recovers as if it had crashed.
    #
    # sac measured the live case: `scitex-cards-pg` declares
    # Type=exec/ExecReload/KillSignal=SIGINT/KillMode=mixed/
    # TimeoutStopSec=120. Adopting it through a renderer that drops those
    # gives CRASH RECOVERY ON EVERY STOP of the store the whole fleet writes
    # to — and the adopted unit still reports `active`, so nothing surfaces.
    if job.kill_signal:
        lines.append(f"KillSignal={job.kill_signal}")
    if job.kill_mode:
        lines.append(f"KillMode={job.kill_mode}")
    if job.timeout_stop_sec is not None:
        lines.append(f"TimeoutStopSec={job.timeout_stop_sec}s")
    if job.exec_reload:
        lines.append(f"ExecReload={job.exec_reload}")
    if job.exec_stop:
        lines.append(f"ExecStop={job.exec_stop}")
    lines.extend(
        [
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )
    return "\n".join(lines)


def _warn_if_anchor_discarded(job: _jobs.JobSpec, on_active: str) -> None:
    """Say out loud when a wall-clock anchor is being thrown away.

    A cron expression like ``30 4 * * *`` names a TIME (04:30 daily). Derived
    into ``OnUnitActiveSec=1d`` it becomes a PERIOD measured from whenever the
    timer last activated, so a host that booted at 15:00 runs its 04:30 job at
    ~15:20 — in the working day the 04:30 was chosen to avoid.

    Nothing about that failure is observable. The unit exists, reports
    ``active (waiting)``, shows a plausible next-elapse and fires at roughly
    the right frequency. It surfaces months later as "why is that report
    late", if at all.

    So the derivation stays (four of sac's live jobs already depend on the
    current cadence, and silently changing them would be the same sin in the
    other direction) — but it stops being SILENT. Requested by sac
    2026-08-17: *"make the discard loud ... that converts a silent
    transformation into a visible one without implementing anything, and it
    would have surfaced this years earlier than either of us did."*

    Only ANCHORED expressions warn. ``*/15 * * * *`` genuinely means "every 15
    minutes" and loses nothing as an interval; ``30 4 * * *`` does. Warning on
    both would train everyone to ignore it.
    """
    fields = (job.schedule or "").split()
    if len(fields) != 5:
        return
    minute, hour = fields[0], fields[1]
    anchored = [
        f"{label}={value}"
        for label, value in (("minute", minute), ("hour", hour))
        if value != "*" and not value.startswith("*/")
    ]
    if not anchored:
        return
    _logger.warning(
        "%s: schedule=%r names a wall-clock anchor (%s) that a systemd "
        "INTERVAL cannot express, so it is being discarded: the unit will "
        "run every %s measured from its last activation, NOT at that time. "
        "Set `on_calendar` (e.g. on_calendar='*-*-* 04:30:00 Asia/Tokyo') "
        "to keep the anchor.",
        job.name,
        job.schedule,
        ", ".join(anchored),
        on_active,
    )


def build_timer_unit(job: _jobs.JobSpec) -> str:
    """Return the ``.timer`` unit text for ``job`` (Persistent=true).

    Only meaningful for ``kind="timer"`` jobs. Calling this on a
    ``kind="service"`` job raises ``ValueError`` — services don't have
    timers; checking up-front avoids writing an inert timer file the
    operator would have to clean up later.
    """
    if job.kind != "timer":
        raise ValueError(
            f"build_timer_unit({job.name!r}): only kind='timer' has a timer; "
            f"got kind={job.kind!r}"
        )
    lines = [
        "[Unit]",
        f"Description=Timer for {job.name}",
        f"Documentation={_DOC_URL}",
        "",
        "[Timer]",
    ]

    # WALL-CLOCK vs INTERVAL is a difference of KIND, not of precision, and
    # until now only one of the two could be expressed.
    #
    # `OnCalendar=*-*-* 06:40:00 Asia/Tokyo` fires at 06:40 local time, every
    # day, forever. `OnUnitActiveSec=1d` fires 24h after the last run — so it
    # walks against the clock as runs are delayed, and carries no timezone at
    # all. Rendering the first as the second does not degrade a schedule; it
    # substitutes a different one, and the substitution is INVISIBLE: the
    # unit exists, reports `active (waiting)`, shows a plausible next-elapse
    # and fires about daily. It surfaces only as "why does the 06:40 report
    # now arrive at 03:00".
    #
    # Found 2026-08-17 by dotfiles, who refused a name-level assurance that
    # their units were adoptable and checked the BODY. `dotfiles-drift-check`
    # is exactly this case.
    #
    # HISTORICAL NOTE, because it is the reason this went unnoticed: JobSpec's
    # own docs described `schedule` as "an optional OnCalendar fallback for
    # kind='timer'" while this renderer only ever averaged it into an
    # interval. Seven of sac's production jobs were declared against the
    # documented behaviour. The docstring is corrected alongside this.
    if job.on_calendar:
        lines.append(f"OnCalendar={job.on_calendar}")
    else:
        on_boot = job.on_boot_sec or DEFAULT_ON_BOOT_SEC
        on_active = job.on_unit_active_sec or derive_on_unit_active_sec(job.schedule)
        _warn_if_anchor_discarded(job, on_active)
        lines.append(f"OnBootSec={on_boot}")
        lines.append(f"OnUnitActiveSec={on_active}")

    lines += [
        # Persistent=true is what makes a missed wall-clock run catch up after
        # a reboot or a suspended laptop, so it matters MORE for OnCalendar
        # than for intervals, not less.
        "Persistent=true",
        f"Unit={job.name}.service",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ]
    return "\n".join(lines)


def systemd_unit_name(job: _jobs.JobSpec) -> str:
    """Return the systemctl enable target for ``job`` (``<name>.timer``
    for timer jobs, ``<name>.service`` for long-running services).
    """
    return f"{job.name}.timer" if job.kind == "timer" else f"{job.name}.service"


# EOF
