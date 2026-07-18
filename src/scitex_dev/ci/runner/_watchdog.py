"""``scitex-dev ci runner validate-health`` — tri-state health signal (NO silent fallback).

Run this on a schedule on the OPERATOR side (a systemd-timer / cron / agent on
your own host) — NOT as an HPC cron. Each tick observes, over the network,
whether the self-hosted runner is actually PROCESSING jobs, and reports an
honest tri-state:

  * ``up``      — a matching online runner exists, the SLURM lease is running,
                  and no CI run has been sitting unprocessed past the grace.
  * ``wedged``  — we COULD observe the fleet and it is not healthy: the runner
                  is offline/absent, the lease is dead, OR (the live failure
                  mode this reland targets) a CI run has been stuck at
                  ``conclusion=None`` — registered-but-not-processing.
  * ``unknown`` — we could NOT observe (a probe errored: gh api / squeue
                  failed). We say so LOUDLY and exit non-zero. We NEVER collapse
                  "can't tell" into "up" — silent absence is exactly the failure
                  this fleet keeps hitting.

Design (per operator directive 2026-06-16, "fail loud, fail fast, no silent
fallback"): on any non-``up`` state the watchdog writes a single ``[ALERT]`` /
``[UNKNOWN]`` line to stderr and exits non-zero so a scheduler surfaces it. It
DELIBERATELY never flips CI to a hosted runner — a silent auto-switch would hide
the outage. Switching to hosted stays a manual, announced
``scitex-dev ci runner use github``. (The "template must not auto-flip to
ubuntu-latest" concern is covered separately by the PS-169 hosted-runner audit
rule; this module is purely the health signal.)

Reland of closed PR #205, re-implemented against the current ci/runner infra and
upgraded from the old binary healthy/unhealthy verdict to the tri-state above.
"""

from __future__ import annotations

import datetime as dt
import json as _json
import subprocess
from dataclasses import dataclass, field
from enum import Enum

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from . import config
from ._preflight import _required_label
from ._status import _lease_status, _runner_status


class RunnerState(str, Enum):
    """Honest tri-state for the self-hosted runner.

    ``str`` mixin so the value serialises to plain JSON as ``"up"`` etc.
    """

    UP = "up"
    WEDGED = "wedged"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthReport:
    """Result of :func:`assess_runner_health` — a state plus its reasons."""

    state: RunnerState
    reasons: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        """True ONLY for ``up``. ``wedged`` and ``unknown`` are both not-healthy."""
        return self.state is RunnerState.UP

    @property
    def exit_code(self) -> int:
        """0 for ``up``, 1 otherwise — so a scheduler surfaces non-``up`` ticks."""
        return 0 if self.state is RunnerState.UP else 1

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "healthy": self.healthy,
            "reasons": list(self.reasons),
        }


def assess_runner_health(
    *,
    runner_query_ok: bool,
    online_labels: list[list[str]],
    lease_query_ok: bool,
    lease_running: bool,
    inflight_query_ok: bool = True,
    oldest_unprocessed_min: float | None = None,
    want_label: str = "scitex-ci",
    stuck_grace_min: float = 15.0,
) -> HealthReport:
    """Pure tri-state health decision — no I/O, so it is unit-testable without mocks.

    Parameters
    ----------
    runner_query_ok : bool
        Whether the GitHub *runners* probe SUCCEEDED. ``False`` means we could
        not tell → ``unknown`` (never ``up``).
    online_labels : list[list[str]]
        Label lists of the currently-ONLINE runners (meaningful only when
        ``runner_query_ok``).
    lease_query_ok : bool
        Whether the SLURM *lease* probe succeeded.
    lease_running : bool
        Whether a RUNNING CI lease exists (meaningful only when
        ``lease_query_ok``).
    inflight_query_ok : bool
        Whether the in-flight *runs* probe succeeded (the ``conclusion=None``
        stuck-run signal).
    oldest_unprocessed_min : float | None
        Age in minutes of the OLDEST CI run still at ``conclusion=None``, or
        ``None`` when there is no such run (meaningful only when
        ``inflight_query_ok``).
    want_label : str
        The label CI workflows target.
    stuck_grace_min : float
        A run unprocessed for at least this many minutes marks the runner
        ``wedged`` — it is registered but not draining the queue.

    Returns
    -------
    HealthReport
        ``state`` is ``unknown`` if ANY probe failed (honest "can't tell", never
        ``up``); otherwise ``wedged`` if any problem is observed, else ``up``.
    """
    # --- honesty gate: any failed probe ⇒ UNKNOWN (never silently "up") ------
    unknown_reasons: list[str] = []
    if not runner_query_ok:
        unknown_reasons.append("runner status probe FAILED (gh api unreachable)")
    if not lease_query_ok:
        unknown_reasons.append("SLURM lease probe FAILED (squeue/ssh unreachable)")
    if not inflight_query_ok:
        unknown_reasons.append("in-flight runs probe FAILED (gh api unreachable)")
    if unknown_reasons:
        return HealthReport(RunnerState.UNKNOWN, unknown_reasons)

    # --- all probes observed: decide up vs wedged ---------------------------
    problems: list[str] = []
    if not any(want_label in labels for labels in online_labels):
        problems.append(f"no ONLINE runner carrying label {want_label!r}")
    if not lease_running:
        problems.append("no RUNNING SLURM CI lease")
    if oldest_unprocessed_min is not None and oldest_unprocessed_min >= stuck_grace_min:
        problems.append(
            f"a CI run has sat unprocessed (conclusion=None) for "
            f"{oldest_unprocessed_min:.0f}min ≥ grace {stuck_grace_min:.0f}min "
            f"— runner appears WEDGED (registered but not processing)"
        )

    if problems:
        return HealthReport(RunnerState.WEDGED, problems)
    return HealthReport(RunnerState.UP, [])


# ---------------------------------------------------------------------------
# I/O probes — thin; each records success/failure so the caller stays honest.
# ---------------------------------------------------------------------------


def _parse_iso(stamp: str) -> dt.datetime:
    """Parse a GitHub ISO-8601 UTC timestamp (``2026-07-18T01:02:03Z``)."""
    return dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def max_age_min(stamps: list[str], now: dt.datetime | None = None) -> float | None:
    """Oldest age in minutes among ``stamps``, or ``None`` when empty.

    Pure (given ``now``) so the stuck-run maths is unit-testable without network.
    """
    if not stamps:
        return None
    now = now or dt.datetime.now(dt.timezone.utc)
    return max((now - _parse_iso(s)).total_seconds() / 60.0 for s in stamps)


def _online_labels_from_runner_status(rstat: dict) -> tuple[bool, list[list[str]]]:
    """Adapt ``_status._runner_status`` output to ``(query_ok, online_labels)``."""
    if rstat.get("error"):
        return False, []
    online = [
        [str(x) for x in (r.get("labels") or [])]
        for r in rstat.get("runners", [])
        if r.get("status") == "online"
    ]
    return True, online


def _lease_running_from_status(lease: dict) -> tuple[bool, bool]:
    """Adapt ``_status._lease_status`` output to ``(query_ok, lease_running)``."""
    if lease.get("error"):
        return False, False
    running = any(j.get("state") == "RUNNING" for j in lease.get("jobs", []))
    return True, running


def _probe_oldest_unprocessed_min(
    repo: str, *, now: dt.datetime | None = None
) -> tuple[bool, float | None]:
    """Return ``(query_ok, oldest_unprocessed_min)`` for CI runs at conclusion=None.

    Queries the workflow-runs endpoint for runs whose ``status`` is not
    ``completed`` (i.e. ``conclusion`` is still null) and returns the age of the
    oldest one. This is the direct signal for the live incident: a self-hosted
    runner registered-but-wedged leaves runs stuck at ``conclusion=None``.
    """
    out = subprocess.run(
        [
            "gh",
            "api",
            f"repos/{repo}/actions/runs",
            "--jq",
            '[.workflow_runs[] | select(.status != "completed") | .created_at]',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if out.returncode != 0:
        return False, None
    try:
        stamps = _json.loads(out.stdout.strip() or "[]")
    except _json.JSONDecodeError:
        return False, None
    return True, max_age_min(stamps, now=now)


def register(group: click.Group) -> None:
    @group.command(
        "validate-health",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Report runner health as a tri-state; FAIL LOUD when not 'up'.",
            description=(
                "\b\n"
                "States & exit codes:\n"
                "  up       (0)  matching online runner + running lease +\n"
                "                queue draining\n"
                "  wedged   (1)  observed but not processing (offline / dead\n"
                "                lease / run stuck at conclusion=None past\n"
                "                the grace)\n"
                "  unknown  (1)  a probe failed — we CANNOT tell, so we\n"
                "                never say 'up'\n"
                "\n"
                "Never flips CI to a hosted runner: a silent auto-switch would "
                "hide the outage. Switching stays a manual, announced "
                "`ci runner use github`. Run it operator-side on a schedule "
                "(systemd-timer / cron) — NOT as an HPC cron."
            ),
            examples=(
                Example(
                    "{prog} ci runner validate-health",
                    "One health tick; exits non-zero unless 'up'.",
                ),
                Example(
                    "{prog} ci runner validate-health --json",
                    "Machine-readable report for a scheduler.",
                ),
                Example(
                    "{prog} ci runner validate-health --grace-min 30",
                    "Allow 30 min of unprocessed queue before 'wedged'.",
                ),
                Example(
                    "{prog} ci runner validate-health --notify-cmd notify-send",
                    "Escalate any non-'up' state operator-side.",
                ),
            ),
            exit_codes=((0, "runner is 'up'"), (1, "'wedged' or 'unknown'")),
        ),
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit a JSON health report on stdout.",
    )
    @click.option(
        "--notify-cmd",
        default=None,
        help="Shell command run on any non-'up' state, with the message as its "
        "last argument (escalation stays operator-side).",
    )
    @click.option(
        "--grace-min",
        type=float,
        default=None,
        help="Minutes a run may sit at conclusion=None before the runner is "
        "reported 'wedged' (default: watchdog.offline_grace_min from config).",
    )
    @click.option(
        "--want-label",
        default=None,
        help="The label CI targets (default: derived from runner.labels).",
    )
    def validate_health(
        as_json: bool,
        notify_cmd: str | None,
        grace_min: float | None,
        want_label: str | None,
    ) -> None:
        cfg = config.load_runner_config()
        repo = cfg["github"]["default_repo"]
        wd = cfg.get("watchdog") or {}
        if grace_min is None:
            grace_min = float(wd.get("offline_grace_min", 15))
        label = want_label or _required_label(cfg)

        runner_ok, online_labels = _online_labels_from_runner_status(
            _runner_status(cfg)
        )
        lease_ok, lease_running = _lease_running_from_status(_lease_status(cfg))
        inflight_ok, oldest_unprocessed = _probe_oldest_unprocessed_min(repo)

        report = assess_runner_health(
            runner_query_ok=runner_ok,
            online_labels=online_labels,
            lease_query_ok=lease_ok,
            lease_running=lease_running,
            inflight_query_ok=inflight_ok,
            oldest_unprocessed_min=oldest_unprocessed,
            want_label=label,
            stuck_grace_min=grace_min,
        )

        if as_json:
            click.echo(_json.dumps({**report.to_dict(), "repo": repo}))

        if report.state is RunnerState.UP:
            if not as_json:
                click.echo(
                    f"ok: runner {label!r} online + SLURM lease running + queue draining"
                )
            return

        tag = "[UNKNOWN]" if report.state is RunnerState.UNKNOWN else "[ALERT]"
        msg = (
            f"{tag} scitex-ci runner {report.state.value} for {repo}: "
            + "; ".join(report.reasons)
            + " — CI will NOT silently fall back to hosted. Fix the runner "
            "(scitex-dev ci runner ensure / up / renew) or switch explicitly with "
            "`scitex-dev ci runner use github`."
        )
        click.echo(msg, err=True)
        if notify_cmd:
            subprocess.run([notify_cmd, msg], timeout=30)
        raise SystemExit(report.exit_code)


# EOF
