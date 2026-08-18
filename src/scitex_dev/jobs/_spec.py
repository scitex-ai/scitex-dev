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
    ALLOWED_SERVICE_TYPES,
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
    service_type
        systemd ``Type=`` for ``kind="service"`` only. ``None`` (the
        default) keeps the historical behaviour, where the renderer
        picks ``notify`` if ``watchdog_sec`` is set and ``simple``
        otherwise. Set it when the daemon's real contract differs —
        ``Type=exec`` (systemd waits for exec, not just fork) or
        ``Type=forking``. MUST be ``None`` for ``timer`` (always
        ``oneshot``) and ``cron`` (no unit at all).

        Setting it to anything but ``"notify"`` alongside
        ``watchdog_sec`` is a contradiction and is REFUSED: the
        watchdog protocol only exists under ``Type=notify``, so the
        pair would emit a ``WatchdogSec`` that can never be satisfied
        and restart the daemon on every interval.
    remain_after_exit
        systemd ``RemainAfterExit=``. ``None`` keeps the historical
        ``no`` for timer-triggered oneshots. Set ``True`` for a unit
        whose *effect* outlives its process (a mount, a one-time
        setup step) so ``systemctl is-active`` answers usefully
        instead of reporting ``inactive`` the moment it succeeds.
        MUST be ``None`` for ``cron``.
    working_directory
        systemd ``WorkingDirectory=``. When ``None`` the directory is
        still derived from ``venv`` exactly as before (the venv's
        parent, i.e. the package root). Set it when the unit must run
        somewhere else — an explicit value WINS over the derived one,
        because a unit that names its own directory is stating a
        requirement, not a preference. MUST be ``None`` for ``cron``.
    environment
        Extra ``Environment=`` lines, each a ``"KEY=value"`` string.
        Emitted AFTER the venv-derived ``VIRTUAL_ENV=``, so a leaf can
        deliberately override it (systemd takes the last assignment of
        a repeated key). Defaults to empty, which emits nothing. A
        tuple rather than a list because JobSpec is frozen. MUST be
        empty for ``cron``.
    environment_file
        systemd ``EnvironmentFile=``. The field whose absence was most
        expensive: a unit's ``EnvironmentFile=`` is frequently the only
        on-disk record of where its secrets and configuration come
        from, so adopting such a unit through a renderer that cannot
        express it does not merely lose a line — it starts the daemon
        with an empty environment while still reporting ``active``.
        Prefix the path with ``-`` for systemd's "ignore if missing"
        semantics. MUST be ``None`` for ``cron``.
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
    # Unit-body fields. Until these existed the renderer DECIDED each of
    # them itself, so a hand-written unit that disagreed could not be
    # adopted without silently changing meaning. Every one defaults to
    # "unset", and unset renders exactly as before — see the
    # byte-identical tests in `tests/scitex_dev/jobs/test__systemd.py`.
    service_type: str | None = None
    remain_after_exit: bool | None = None
    working_directory: str | None = None
    environment: tuple[str, ...] = ()
    environment_file: str | None = None

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
        if (
            self.service_type is not None
            and self.service_type not in ALLOWED_SERVICE_TYPES
        ):
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service').service_type="
                f"{self.service_type!r} not in "
                f"{sorted(ALLOWED_SERVICE_TYPES)}"
            )
        if self.watchdog_sec is not None and self.service_type not in (
            None,
            "notify",
        ):
            # The watchdog protocol EXISTS ONLY under Type=notify: the
            # daemon proves liveness with sd_notify(WATCHDOG=1), which a
            # non-notify unit has no channel to send. Emitting both would
            # produce a WatchdogSec that can never be satisfied, so systemd
            # would kill and restart the daemon every interval forever.
            # Refuse the pair rather than silently dropping either half —
            # dropping the watchdog hides a requested guard, and forcing
            # notify breaks a daemon that never sends READY=1.
            raise ValueError(
                f"JobSpec({self.name!r}, kind='service') sets watchdog_sec="
                f"{self.watchdog_sec!r} with service_type="
                f"{self.service_type!r}. WatchdogSec only works under "
                f"Type=notify. Either set service_type='notify' (and send "
                f"sd_notify(WATCHDOG=1) pings), or drop watchdog_sec."
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
        if self.service_type is not None:
            # A timer's body IS a oneshot — that is what "run this, then
            # stop" means. Letting a leaf name a different Type= here would
            # produce a unit the timer cannot drive correctly.
            raise ValueError(
                f"JobSpec({self.name!r}, kind='timer').service_type must be "
                f"None (a timer-triggered unit is always Type=oneshot). "
                f"Got: {self.service_type!r}"
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
        # The unit-body fields describe a systemd unit. A cron job has no
        # unit, so a set value here would be silently dropped at render
        # time — the exact silent-misconfiguration trap the rest of this
        # validator exists to prevent.
        for field, value, empty in (
            ("service_type", self.service_type, None),
            ("remain_after_exit", self.remain_after_exit, None),
            ("working_directory", self.working_directory, None),
            ("environment", self.environment, ()),
            ("environment_file", self.environment_file, None),
        ):
            if value != empty:
                raise ValueError(
                    f"JobSpec({self.name!r}, kind='cron').{field} must be "
                    f"{empty!r} (systemd-only field; cron lines are inert "
                    f"text in a crontab). Got: {value!r}"
                )

