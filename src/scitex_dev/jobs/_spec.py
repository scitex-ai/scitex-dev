#!/usr/bin/env python3
"""The JobSpec data contract: one scheduled job, and what makes it valid.

Split out of ``jobs/__init__.py`` so the package facade holds DISCOVERY
and this module holds the CONTRACT — one responsibility each. The class
body was moved verbatim: no field, validator or message changed. Import
it from either place — ``jobs/__init__.py`` re-exports ``JobSpec``, so
every existing caller keeps working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._kinds import (
    ACCEPTED_KINDS,
    ALLOWED_KINDS,
    ALLOWED_RESTART_POLICIES,
    INTENT_KINDS,
    INTENT_TO_KIND,
    canonical_kind,
)


@dataclass(frozen=True)
class JobSpec:
    """One scheduled job, shared across the SciTeX ecosystem.

    Fields
    ------
    name
        Package-prefixed unique id, e.g. ``"sac.accounts-refresh"``.
    kind
        One of ``"service"``, ``"timer"``, ``"cron"``. See the module
        docstring for what each kind means and which fields apply.
    schedule
        For ``kind="cron"``: a 5-field cron expression. For
        ``kind="timer"``: derives an ``OnUnitActiveSec`` INTERVAL, averaged
        from the expression — it is NOT rendered as an ``OnCalendar``, so any
        wall-clock anchor in it is DISCARDED (loudly, since 2026-08-17). Use
        ``on_calendar`` to keep the anchor. This entry previously claimed the
        OnCalendar behaviour; it was never implemented, and live jobs were
        declared against the wrong sentence. For ``kind="service"``: MUST be
        the empty string (services run continuously).
    command
        Shell command to execute. Required for every kind.
    description
        Human-readable summary shown in ``list`` output.
    on_boot_sec
        systemd timer ``OnBootSec`` (timer) or service start delay
        (service). Ignored for ``kind="cron"``. Format: systemd
        duration string (e.g. ``"15s"``, ``"15min"``, ``"4h"``).
    on_unit_active_sec
        systemd timer ``OnUnitActiveSec`` — required for
        ``kind="timer"`` unless ``schedule`` is set (then derived).
        MUST be ``None`` for ``service`` and ``cron`` kinds.
    timeout_sec
        Hard timeout in seconds; maps to systemd ``TimeoutStartSec``.
        Applies to ``service`` (start) and ``timer`` (oneshot exec)
        kinds. ``None`` means systemd's default.
    restart_policy
        systemd ``Restart=`` value for ``kind="service"`` only —
        controls automatic restart on exit/failure. Defaults to
        ``"no"`` (no restart). MUST stay ``"no"`` for ``timer`` and
        ``cron`` kinds.
    watchdog_sec
        systemd ``WatchdogSec`` for ``kind="service"`` only — the
        liveness-ping interval that guards against *hangs* (a crash is
        already covered by ``Restart=``; a hang is not). Defaults to
        ``None`` (no watchdog).

        CRITICAL CAVEAT — opt-in on purpose. ``WatchdogSec`` does
        NOTHING unless the daemon periodically calls
        ``sd_notify(WATCHDOG=1)`` under ``Type=notify``. A plain
        ``Type=simple`` daemon that never pings would be *killed and
        restarted every ``WatchdogSec`` seconds* by systemd — a
        footgun. So a JobSpec must EXPLICITLY set ``watchdog_sec`` to
        request it; when set, the unit builder emits ``Type=notify`` +
        ``WatchdogSec=<N>s`` and the LEAF is responsible for sending
        the pings. When unset, the unit stays ``Type=simple`` and
        relies on ``Restart=`` alone (crashes, not hangs). MUST be
        ``None`` for ``timer`` and ``cron`` kinds.
    venv
        Optional path to the venv directory that OWNS ``command``,
        e.g. ``"/home/ywatanabe/proj/scitex-todo/.venv"``. "Leaf owns
        its own venv": a supervised child is a DIFFERENT package from
        scitex-dev (which runs the supervisor), so resolving the
        child's executable via the supervisor's own
        ``sys.executable`` (the historical default) can pick up a
        missing, stale, or wrong-version binary. When set, both the
        systemd unit builder (``ExecStart=``) and the ``ecosystem
        run`` supervisor (``subprocess.Popen`` argv) resolve the
        command as ``<venv>/bin/<head>`` instead, set ``cwd`` to the
        venv's parent directory (the package root), and export
        ``VIRTUAL_ENV=<venv>`` in the child's environment — mirroring
        what a normal ``source <venv>/bin/activate`` would do.
        Defaults to ``None``, which keeps the historical behavior
        (resolve via the supervisor's own interpreter / PATH) for
        every existing JobSpec — fully backward compatible.
    """

    name: str
    kind: str
    schedule: str
    command: str
    description: str
    on_boot_sec: str | None = None
    on_unit_active_sec: str | None = None
    timeout_sec: int | None = None
    restart_policy: str = "no"
    watchdog_sec: int | None = None
    venv: str | None = None
    on_calendar: str | None = None
    # Stop/lifecycle semantics for kind="service". Rationale for each lives
    # beside its emission in `_systemd.py::build_service_unit` — omitting
    # them is not cosmetic: systemd's default stop is SIGTERM then SIGKILL,
    # so a daemon wanting SIGINT gets a hard kill and recovers as if crashed.
    kill_signal: str | None = None
    kill_mode: str | None = None
    timeout_stop_sec: int | None = None
    exec_reload: str | None = None
    exec_stop: str | None = None
    restart_prevent_exit_status: str | None = None

    def __post_init__(self) -> None:
        # Normalise the INTENT spellings BEFORE validating, so the rest of
        # this class — and every consumer downstream — only ever sees the
        # stored vocabulary. Frozen dataclass, hence object.__setattr__.
        canonical = canonical_kind(self.kind, self.schedule)
        if canonical != self.kind:
            object.__setattr__(self, "kind", canonical)
        # Run the validator at construction time so a malformed leaf
        # crashes EARLY — never let a silently-broken unit reach the
        # systemd installer (or worse, a running host).
        self.validate()

    @property
    def intent(self) -> str:
        """What this job DOES, independent of scheduler: daemon | periodic.

        DERIVED from ``kind``, never stored beside it. New code can read the
        intent-level vocabulary without any provider migrating, and there is
        no second field that could drift out of agreement with the first.
        """
        return "daemon" if self.kind == "service" else "periodic"

    # ----------------------------------------------------------------- #
    # Validation                                                        #
    # ----------------------------------------------------------------- #
    def validate(self) -> None:
        """Raise ``ValueError`` if the field combination is invalid.

        Called from ``__post_init__`` so a malformed leaf crashes at
        ``JobSpec(...)`` construction (NOT later in the systemd
        installer when a half-written unit hits the disk).

        The rule set is the documented kind-taxonomy above, flattened
        into explicit checks so the error messages name the precise
        broken invariant.
        """
        if not self.name:
            raise ValueError("JobSpec.name must be non-empty")
        if not self.command:
            raise ValueError(
                f"JobSpec({self.name!r}).command must be non-empty"
            )
        if self.kind not in ALLOWED_KINDS:
            raise ValueError(
                f"JobSpec({self.name!r}).kind={self.kind!r} not in "
                f"{sorted(ACCEPTED_KINDS)}. The intent spellings "
                f"{sorted(INTENT_KINDS)} are accepted too and normalise to "
                f"{INTENT_TO_KIND} — 'periodic' means a systemd timer; with "
                f"a 'schedule' it is ambiguous and rejected, so say "
                f"'cron' or 'timer' explicitly."
            )
        if self.restart_policy not in ALLOWED_RESTART_POLICIES:
            raise ValueError(
                f"JobSpec({self.name!r}).restart_policy="
                f"{self.restart_policy!r} not in "
                f"{sorted(ALLOWED_RESTART_POLICIES)}"
            )

        if self.kind == "service":
            self._validate_service()
        elif self.kind == "timer":
            self._validate_timer()
        elif self.kind == "cron":
            self._validate_cron()

    def _validate_service(self) -> None:
        # A service is a long-running unit. Schedules / timer fields
        # don't apply — surfacing them at install-time would be a
        # silent-misconfiguration trap.
        if self.schedule != "":
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service').schedule must be "
                f"empty (services aren't scheduled — they run "
                f"continuously). Got: {self.schedule!r}"
            )
        if self.on_unit_active_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service')."
                f"on_unit_active_sec must be None (Timer-only field; "
                f"services use Restart= for keepalive, not a timer). "
                f"Got: {self.on_unit_active_sec!r}"
            )
        if self.watchdog_sec is not None and self.watchdog_sec <= 0:
            # A non-positive interval is meaningless and, worse, would
            # produce a WatchdogSec=0s that systemd treats as "disabled"
            # while implying the leaf opted in — a confusing half-state.
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service').watchdog_sec "
                f"must be a positive number of seconds when set. "
                f"Got: {self.watchdog_sec!r}"
            )

    def _validate_timer(self) -> None:
        # A systemd Timer needs SOMETHING to tell it when to fire.
        # Accept either an explicit on_unit_active_sec OR a cron-style
        # schedule we can derive from. Rejecting both is the early-
        # crash that catches "I forgot to set the cadence".
        # `on_calendar` is the THIRD way to say when, and the only one that
        # names a wall-clock time rather than a period.
        if not (self.on_unit_active_sec or self.schedule or self.on_calendar):
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer') needs one of "
                f"on_calendar (wall-clock, '*-*-* 04:30:00 Asia/Tokyo'), "
                f"on_unit_active_sec (interval), or schedule (cron expr, "
                f"derived to an interval) — all three are empty."
            )
        if self.restart_policy != "no":
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer').restart_policy "
                f"must be 'no' (timers fire oneshot services; Restart= "
                f"doesn't apply). Got: {self.restart_policy!r}"
            )
        if self.watchdog_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer').watchdog_sec "
                f"must be None (WatchdogSec guards long-running services, "
                f"not oneshot timer bodies). Got: {self.watchdog_sec!r}"
            )

    def _validate_cron(self) -> None:
        # Cron lines are inert text in the user's crontab. The systemd
        # fields would be meaningless; insist they're None so a
        # mis-set field flags up as a clear bug rather than silently
        # being dropped.
        if not self.schedule:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').schedule must be a "
                f"5-field cron expression (got empty)"
            )
        fields = self.schedule.split()
        if len(fields) != 5:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').schedule must have "
                f"exactly 5 cron fields, got {len(fields)}: "
                f"{self.schedule!r}"
            )
        if self.on_boot_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').on_boot_sec must "
                f"be None (cron has no boot concept). Got: "
                f"{self.on_boot_sec!r}"
            )
        if self.on_unit_active_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron')."
                f"on_unit_active_sec must be None (systemd-only field). "
                f"Got: {self.on_unit_active_sec!r}"
            )
        if self.restart_policy != "no":
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').restart_policy "
                f"must be 'no' (cron has no restart concept). Got: "
                f"{self.restart_policy!r}"
            )
        if self.watchdog_sec is not None:
            raise ValueError(
                f"JobSpec({self.name!r}, kind='cron').watchdog_sec "
                f"must be None (systemd-only field). Got: "
                f"{self.watchdog_sec!r}"
            )

