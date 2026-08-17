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
import os
import shlex
import shutil
import sys
import warnings
from pathlib import Path

from .. import jobs as _jobs

DEFAULT_ON_BOOT_SEC = "15min"
DEFAULT_ON_UNIT_ACTIVE_SEC = "1h"

# Documentation URL stamped into generated units (operator breadcrumb).
_DOC_URL = "https://github.com/scitex-ai/scitex-dev"

_logger = logging.getLogger(__name__)


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


def _on_boot_sec_to_seconds(value: str) -> int:
    """Best-effort parse of a systemd duration string into integer seconds.

    Recognises the small set of suffixes we actually use
    (``s`` / ``min`` / ``h``). Anything we don't recognise returns
    ``0`` so ``ExecStartPre=/bin/sleep 0`` is a harmless no-op rather
    than a unit-write failure.
    """
    text = value.strip().lower()
    if text.endswith("min"):
        n = _safe_int(text[:-3])
        return (n or 0) * 60
    if text.endswith("h"):
        n = _safe_int(text[:-1])
        return (n or 0) * 3600
    if text.endswith("s"):
        n = _safe_int(text[:-1])
        return n or 0
    n = _safe_int(text)
    return n or 0


def _interpreter_bindir() -> Path:
    """Return ``Path(sys.executable).parent`` — the bin/ holding sibling
    console scripts for the interpreter currently running this process.

    Indirection exists so tests can monkeypatch it without having to
    relocate the real interpreter.
    """
    return Path(sys.executable).resolve().parent


def resolve_execstart(
    command: str,
    *,
    venv: str | None = None,
    which=shutil.which,
    interpreter_bindir=_interpreter_bindir,
) -> str:
    """Return an ``ExecStart=`` value with the first token absolutised.

    systemd ``--user`` services run under a deliberately minimal PATH
    (``/usr/local/bin:/usr/bin:/bin``) that excludes the operator's
    Python venv and most ecosystem installs. If we emit a relative
    command name like ``scitex-todo board --port 8051`` the unit fails
    to start with ``status=127/EXEC`` (command not found) and any
    leaf service silently flaps.

    Resolution rules (tried in order — first match wins):

    0. **Per-job venv pin** — ``Path(venv) / "bin" / head`` when
       ``venv`` is given (typically ``JobSpec.venv``). "Leaf owns its
       own venv": a cross-package supervised child should resolve
       against ITS OWN venv, not the supervisor's. Takes priority over
       every other rule below. Falls through to them if the pinned
       venv doesn't actually contain the binary (e.g. a stale pin) so
       a misconfigured pin degrades to the old behavior instead of a
       hard failure.
    1. **Interpreter sibling-bin** — ``Path(sys.executable).parent / head``.
       The process that *writes* the unit is the same interpreter that
       installed the console scripts. Its sibling ``bin/`` therefore
       reliably holds ``scitex-todo``, ``scitex-dev``, ``sac``, etc.,
       even when ``ecosystem up`` was invoked via the venv's absolute
       interpreter (no ``activate``) and so the ambient PATH lacks
       the venv's ``bin/`` (the live bug observed on ywata-note-win,
       where ``scitex-todo.wake-watcher.service`` was written with
       ``ExecStart=/usr/bin/env scitex-todo`` and crash-looped at
       ``status=127`` for ~12 h because systemd user PATH lacks
       ``~/.env-3.11/bin``).
    2. **PATH lookup** — :func:`shutil.which` against the ambient PATH.
       Catches operator binaries installed outside the interpreter's
       bin (``/usr/local/bin/...``, ``~/.local/bin/...``, etc.).
    3. **/usr/bin/env fallback** — last resort. Emits a *loud*
       :class:`UserWarning` so the bring-up log makes it obvious the
       resolution missed; the unit will still fail to start with
       ``status=127`` under systemd's minimal PATH, but the operator
       has a breadcrumb.

    Pass-throughs:

    * If the first token is already absolute (starts with ``/``), pass
      through unchanged — the leaf has been explicit.
    * Empty ``command`` returns ``command`` verbatim.

    Args/tokens are preserved verbatim via ``shlex``-style splitting
    + re-joining so a quoted arg with spaces survives the round-trip.

    The ``which`` and ``interpreter_bindir`` keywords are test seams
    (fake-callables); the production defaults are :func:`shutil.which`
    and :func:`_interpreter_bindir`.
    """
    tokens = shlex.split(command)
    if not tokens:
        return command
    head, *tail = tokens
    if head.startswith("/"):
        return command

    # 0. Per-job venv pin — highest priority. The leaf DECLARED which
    #    venv owns this command; trust that over the supervisor's own
    #    interpreter or ambient PATH.
    if venv:
        pinned = Path(venv) / "bin" / head
        if pinned.is_file() and os.access(pinned, os.X_OK):
            return shlex.join([str(pinned), *tail])

    # 1. Interpreter sibling-bin probe — most reliable for console
    #    scripts installed alongside the running interpreter.
    try:
        candidate = interpreter_bindir() / head
    except Exception:  # pragma: no cover — defensive only
        candidate = None
    if candidate is not None and candidate.is_file() and os.access(candidate, os.X_OK):
        return shlex.join([str(candidate), *tail])

    # 2. PATH lookup.
    resolved = which(head)
    if resolved:
        return shlex.join([resolved, *tail])

    # 3. Fallback — emit a LOUD warning so a bring-up log makes the
    #    miss obvious. systemd will still fail with exec=127, but
    #    the operator has a clear breadcrumb instead of a silent flap.
    warnings.warn(
        f"resolve_execstart: could not resolve {head!r} via "
        f"sys.executable's bin ({Path(sys.executable).parent}) nor PATH; "
        f"falling back to '/usr/bin/env {head}'. The systemd user unit "
        f"will likely fail with status=127 because user PATH is minimal. "
        f"Install the binary in the interpreter's bin/ or on PATH before "
        f"running 'ecosystem up'.",
        UserWarning,
        stacklevel=2,
    )
    return f"/usr/bin/env {command}"


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
        "RemainAfterExit=no",
    ]
    if job.venv:
        lines.append(f"WorkingDirectory={Path(job.venv).parent}")
        lines.append(f"Environment=VIRTUAL_ENV={job.venv}")
    if job.timeout_sec is not None:
        lines.append(f"TimeoutStartSec={job.timeout_sec}s")
    lines.append("")
    return "\n".join(lines)


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
        # Type=notify ONLY when a watchdog is requested — a Type=notify
        # unit whose ExecStart never calls sd_notify(READY=1) would sit
        # in "activating" until TimeoutStartSec and fail, so we must NOT
        # flip to notify for daemons that don't opt in.
        "Type=notify" if use_watchdog else "Type=simple",
    ]
    if job.on_boot_sec:
        seconds = _on_boot_sec_to_seconds(job.on_boot_sec)
        if seconds > 0:
            lines.append(f"ExecStartPre=/bin/sleep {seconds}")
    if job.venv:
        lines.append(f"WorkingDirectory={Path(job.venv).parent}")
        lines.append(f"Environment=VIRTUAL_ENV={job.venv}")
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
