#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Registry of managed cron jobs for `scitex-dev cron`.

A "managed job" is identified by a short slug (the ``name`` argument
passed to ``install`` / ``remove`` / ``status``). The registry maps that
slug to a 5-field cron schedule and the literal shell command that gets
materialised into the user's crontab — tagged with
``# scitex-dev cron: <name>`` so we can find it again.

Why a registry (vs. a free-form ``add <schedule> <command>``):

  * Ecosystem-wide cron jobs are *known* artifacts that other parts of
    the ecosystem expect to be present (e.g. the ci-watch loop is part of
    how sac agents notice they have a fix-forward turn to take).
  * Operators install / remove by *name*, not by reconstructing the
    schedule + command line from memory.
  * Adding a new job is a one-entry diff here, plus the implementation
    module under this package. Nothing else in the CLI changes.

To add a new managed job:

  1. Implement the job. Either as a Python entry point invoked via the
     console script (``scitex-dev cron run <name>``) or as a standalone
     shell command — either is fine; the registry just records the
     resulting cron line.
  2. Add an entry to ``JOB_REGISTRY`` below: ``name → (schedule, command,
     description)``. Keep the schedule conservative (every 5-15 minutes
     is plenty for poll loops).
  3. Write the unit test that pins the registry entry — see
     ``tests/scitex_dev/_cli/cron/test__jobs.py``.

The registry is intentionally a module-level dict (no YAML loader, no
dynamic discovery): one diff, one commit, one PR.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class JobSpec:
    """One managed cron job."""

    name: str
    schedule: str
    command: str
    description: str


def _ci_watch_command() -> str:
    """The shell line installed for the ``ci-watch`` cron job.

    We invoke the console script (``scitex-dev cron exec ci-watch``) so
    the line stays stable across virtual-env shuffles — ``scitex-dev`` is
    on PATH wherever this CLI is installed.

    Output is appended to ``~/.scitex/dev/logs/cron-ci-watch.log``; size
    rotation is intentionally not done here (cron-watch is low-volume
    and the log is operator-facing, not a hot path).
    """
    log = "$HOME/.scitex/dev/logs/cron-ci-watch.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec ci-watch >> {log} 2>&1"


def _worktree_gc_command() -> str:
    """The shell line installed for the ``worktree-gc`` cron job.

    Same shape as ``ci-watch`` / ``quota-keepalive``: invoke the console
    script so the line stays stable across virtual-env shuffles,
    ``mkdir -p`` the log dir first, append output to a per-job log.

    Schedule rationale: every 6 hours is conservative — a single sweep
    is short (find git dirs, ``git worktree list``, mtime check), and
    proj-scitex-agent-container is concurrently working on the
    RELOCATION half (stopping ``.claude/worktrees`` from being created
    in the first place), so the cleanup loop's load will fall over
    time. Until that ships, 4 sweeps per day keeps the orphan count
    bounded without spending CI on a constant background walk.
    """
    log = "$HOME/.scitex/dev/logs/cron-worktree-gc.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec worktree-gc >> {log} 2>&1"


def _quota_keepalive_command() -> str:
    """The shell line installed for the ``quota-keepalive`` cron job.

    Same shape as ``ci-watch``: invoke the console script so the line
    stays stable across virtual-env shuffles, ``mkdir -p`` the log dir
    first, append output to a per-job log.

    The crontab schedule is ``*/30 * * * *`` (every 30 minutes), but the
    body self-gates to fire only every 2.5 hours — see
    ``_quota_keepalive.run_once`` for why 2.5 h cannot be one cron
    interval and how the timestamp gate enforces exact spacing.
    """
    log = "$HOME/.scitex/dev/logs/cron-quota-keepalive.log"
    return (
        f"mkdir -p $(dirname {log}); scitex-dev cron exec quota-keepalive >> {log} 2>&1"
    )


def _cred_distribute_command() -> str:
    """The shell line installed for the ``cred-distribute`` cron job.

    Same shape as ``ci-watch`` / ``worktree-gc`` / ``task-harvest``:
    invoke the console script so the line stays stable across
    virtual-env shuffles, ``mkdir -p`` the log dir first, append output
    to a per-job log.

    Schedule rationale: every 2 hours (``0 */2 * * *``) — matches the
    operator's pre-existing ad-hoc ``spartan-cred-push`` cadence (the
    stop-gap this job subsumes) and is conservative for credentials
    that turn over on a multi-hour window. Operator-tunable: change
    the schedule HERE (one diff + one test) and re-install.

    Body lives in ``_cred_distribute.run_once``; the per-host list and
    credential selector are read from
    ``~/.scitex/dev/cred-distribute.yaml`` so switching behaviour does
    not require any code change. Coordinates with
    proj-scitex-agent-container which is concurrently building the
    ``sac accounts distribute`` capability — the body is fail-open
    until that capability lands.
    """
    log = "$HOME/.scitex/dev/logs/cron-cred-distribute.log"
    return (
        f"mkdir -p $(dirname {log}); scitex-dev cron exec cred-distribute >> {log} 2>&1"
    )


def _task_harvest_command() -> str:
    """The shell line installed for the ``task-harvest`` cron job.

    Same shape as ``ci-watch`` / ``worktree-gc`` / ``quota-keepalive``:
    invoke the console script so the line stays stable across
    virtual-env shuffles, ``mkdir -p`` the log dir first, append
    output to a per-job log.

    Schedule rationale: every 6 hours (``0 */6 * * *``) — the harvest
    walks the shared task store, re-checks blockers, and (in the
    follow-up that adds Phase-2 dispatch) a2a-escalates RUNNABLE
    tasks to their owning agents. 4 sweeps per day keeps
    consumption-rate pressure on the board without spamming agent
    inboxes. Operator-tunable: change the schedule HERE (one diff +
    one test) and re-install.

    Body lives in ``_task_harvest.run_once``; the operator-facing
    PROTOCOL lives in ``scitex_todo._skills.scitex-todo.40_task-harvest``
    (the skill the operator commissioned, scitex-todo PR #72).
    """
    log = "$HOME/.scitex/dev/logs/cron-task-harvest.log"
    return f"mkdir -p $(dirname {log}); scitex-dev cron exec task-harvest >> {log} 2>&1"


def _spartan_conn_monitor_command() -> str:
    """The shell line installed for the ``spartan-conn-monitor`` cron job.

    Same shape as the other jobs: invoke the console script so the line stays
    stable across virtual-env shuffles, ``mkdir -p`` the log dir, append to a
    per-job log. Schedule ``*/30 * * * *`` (every 30 min) — light (one
    multiplexed ssh + pgrep/ps/who per login node), enough to catch a
    connection/agent regression long before the HPC admin would. Body in
    ``_spartan_conn_monitor.run_once``; metrics history is the TSV at
    ``~/.scitex/dev/runtime/spartan-conn-monitor.tsv``.
    """
    log = "$HOME/.scitex/dev/logs/cron-spartan-conn-monitor.log"
    return (
        f"mkdir -p $(dirname {log}); "
        f"scitex-dev cron exec spartan-conn-monitor >> {log} 2>&1"
    )


# 1 MiB — the size at which the per-job log is rotated to ``<log>.1``
# before the job runs. Mirrors ``_creds._cron._LOG_ROTATE_BYTES`` (the
# ad-hoc creds-rotate installer this federation subsumes) so the
# managed line keeps the exact rotation behaviour the host line had.
_LOG_ROTATE_BYTES = 1_048_576


def _log_rotate_guard(log: str) -> str:
    """Inline shell that rotates ``log`` to ``<log>.1`` when it exceeds 1 MiB.

    Same shell-fu as ``_creds._cron.build_cron_line``: when the log grows
    past ``_LOG_ROTATE_BYTES`` move it aside so the running line re-opens a
    fresh file. Returned with a trailing ``; `` so it composes directly in
    front of the command body.
    """
    return (
        f'[ -f {log} ] && [ "$(stat -c%s {log} 2>/dev/null || echo 0)" '
        f"-gt {_LOG_ROTATE_BYTES} ] && mv {log} {log}.1; "
    )


def _creds_rotate_all_command() -> str:
    """The shell line installed for the ``creds-rotate-all`` cron job.

    This federates the operator's pre-existing ad-hoc crontab line
    (tagged ``# scitex-dev creds-rotate (managed)`` — see
    ``_creds._cron``) into the managed block. The body is identical to
    that installer's: ``mkdir -p`` the log dir, run the 1-MiB log-
    rotation guard, then run ``scitex-dev creds rotate-all --yes``
    appending to ``~/.scitex/dev/logs/creds-rotate.log``.

    NOTE the log slug is ``creds-rotate.log`` (NO ``cron-`` prefix) to
    match the existing ad-hoc line byte-for-byte — the line this entry
    retires writes to exactly that path, and operators / dashboards that
    tail it must keep working across the move.
    """
    log = "$HOME/.scitex/dev/logs/creds-rotate.log"
    return (
        f"mkdir -p $(dirname {log}); {_log_rotate_guard(log)}"
        f"scitex-dev creds rotate-all --yes >> {log} 2>&1"
    )


def _ci_runner_ensure_command() -> str:
    """The shell line installed for the ``ci-runner-ensure`` cron job.

    Federates the operator's ad-hoc ``ci-runner-ensure`` crontab line into
    the managed block. The job body is the standalone host script
    ``~/.scitex/dev/ci-runner-ensure-cron.sh`` (already deployed on the
    host); this entry only records the resulting cron line so the
    federation materialises it. ``mkdir -p`` the log dir first, then run
    the script appending to ``~/.scitex/dev/logs/ci-runner-ensure.log``.
    """
    log = "$HOME/.scitex/dev/logs/ci-runner-ensure.log"
    script = "$HOME/.scitex/dev/ci-runner-ensure-cron.sh"
    return f"mkdir -p $(dirname {log}); {script} >> {log} 2>&1"


def _ci_runner_workgc_command() -> str:
    """The shell line installed for the ``ci-runner-workgc`` cron job.

    Federates the operator's ad-hoc ``ci-runner-workgc`` crontab line into
    the managed block. The job body is the standalone host script
    ``~/.scitex/dev/ci-runner-workgc-cron.sh`` (already deployed on the
    host); this entry only records the resulting cron line so the
    federation materialises it. ``mkdir -p`` the log dir first, then run
    the script appending to ``~/.scitex/dev/logs/ci-runner-workgc.log``.
    """
    log = "$HOME/.scitex/dev/logs/ci-runner-workgc.log"
    script = "$HOME/.scitex/dev/ci-runner-workgc-cron.sh"
    return f"mkdir -p $(dirname {log}); {script} >> {log} 2>&1"


def _ecosystem_sync_command() -> str:
    """The shell line installed for the ``ecosystem-sync`` cron job.

    Runs the WRITE self-pull ``scitex-dev ecosystem sync --yes`` (see
    ``_cmds/_sync.py``), which fast-forwards every editable checkout's
    ``develop`` to ``origin/develop``. Safe by construction: develop-only,
    ``git merge --ff-only``, and dirty / off-develop / diverged checkouts
    are reported and SKIPPED — never clobbered, so the operator's
    un-pushed work is never touched.

    Why this is a MANAGED job and not merely an available command: the
    ecosystem runs on editable installs that import their own working
    tree, but ``origin/develop`` advances on its own (CI commits docs-HTML
    and version bumps back). Without a periodic self-pull a checkout
    silently serves stale code — the workstation's own ``scitex-dev``
    checkout was found 18 commits behind tag v0.21.0 (2026-07-01) and the
    Spartan runner 145 behind. Scheduling the sweep closes that self-pull
    leg of the loop so no editable install drifts unnoticed again.

    ``mkdir -p`` the log dir, run the 1-MiB log-rotation guard (a sweep
    over ~60 repos writes a table each run), then append output to
    ``~/.scitex/dev/logs/cron-ecosystem-sync.log``.
    """
    log = "$HOME/.scitex/dev/logs/cron-ecosystem-sync.log"
    return (
        f"mkdir -p $(dirname {log}); {_log_rotate_guard(log)}"
        f"scitex-dev ecosystem sync --yes >> {log} 2>&1"
    )


JOB_REGISTRY: Mapping[str, JobSpec] = {
    "ci-watch": JobSpec(
        name="ci-watch",
        schedule="*/10 * * * *",
        command=_ci_watch_command(),
        description=(
            "Poll each sac agent's owned repo for CI red on develop; "
            "dispatch a fix-forward A2A turn to the responsible agent "
            "when failures are seen."
        ),
    ),
    "quota-keepalive": JobSpec(
        name="quota-keepalive",
        # Crontab ticks every 30 min; the body self-gates to a 2.5-hour
        # cadence (2.5 h is not expressible as a single cron interval).
        schedule="*/30 * * * *",
        command=_quota_keepalive_command(),
        description=(
            "Fire a trivial 'hello' turn every 2.5 hours (self-gated) to "
            "pre-start Claude's rolling 5-hour quota window, so real work "
            "begins against a window that is already partway elapsed."
        ),
    ),
    "worktree-gc": JobSpec(
        name="worktree-gc",
        # Every 6 hours: 4 sweeps per day, generous headroom over the
        # mtime threshold (default 3 days). See _worktree_gc_command's
        # docstring for the schedule rationale.
        schedule="0 */6 * * *",
        command=_worktree_gc_command(),
        description=(
            "Periodic cleanup of stale `.claude/worktrees/` directories "
            "left behind by subagents. mtime-gated, git-worktree-aware, "
            "never touches the operator's `.worktrees/`. See _worktree_gc."
        ),
    ),
    "task-harvest": JobSpec(
        name="task-harvest",
        # Every 6 hours: 4 harvest sweeps per day over the shared
        # ~/.scitex/todo/tasks.yaml board. Matches the q6h default the
        # operator picked in the skill (scitex-todo PR #72,
        # 40_task-harvest.md). Operator may want q1h during a busy
        # phase or q12h during a quiet phase — change THIS schedule
        # (one diff + one test) and re-install.
        schedule="0 */6 * * *",
        command=_task_harvest_command(),
        description=(
            "scitex-todo task-harvest: classify the shared "
            "~/.scitex/todo/tasks.yaml (blocked vs runnable + blocker "
            "kind), log an audit line, return a structured result the "
            "follow-up PRs extend with Phase-1 walk + Phase-2 a2a "
            "dispatch. Protocol: skill 40_task-harvest. See "
            "_task_harvest.run_once."
        ),
    ),
    "cred-distribute": JobSpec(
        name="cred-distribute",
        # Every 2 hours on the hour. Matches the operator's pre-
        # existing ad-hoc spartan-cred-push cadence (the host crontab
        # marker this job subsumes per directive 2026-06-11) and is
        # conservative for credentials that turn over on a multi-hour
        # window. The per-host target list lives in
        # ~/.scitex/dev/cred-distribute.yaml — switching behaviour
        # (add/remove host, change account selector) is a YAML edit
        # alone, no code change required.
        schedule="0 */2 * * *",
        command=_cred_distribute_command(),
        description=(
            "Push the freshest Claude credentials to peer hosts via "
            "`sac accounts distribute --to-host <h> --account <a>`. "
            "Host list + credential selector live in "
            "~/.scitex/dev/cred-distribute.yaml so behaviour is "
            "switched by config alone. Subsumes the host-side ad-hoc "
            "push-freshest-cred-to-spartan.sh (crontab marker "
            "# spartan-cred-push). Fail-open while "
            "proj-scitex-agent-container is still landing the "
            "`sac accounts distribute` capability. See "
            "_cred_distribute.run_once."
        ),
    ),
    "spartan-conn-monitor": JobSpec(
        name="spartan-conn-monitor",
        # Every 30 min. Light: one multiplexed ssh + pgrep/ps/who per login
        # node. Watches the ywatanabe user's ssh-agent / connection / proc
        # footprint on the Spartan login nodes (2026-06-17 admin incident) and
        # phones the operator if a threshold is crossed. Replaces the
        # session-bound monitor loop, which died on context compaction.
        schedule="*/30 * * * *",
        command=_spartan_conn_monitor_command(),
        description=(
            "Poll the 3 Spartan login nodes for the ywatanabe user's "
            "ssh-agents / login sessions / total procs / srun; append a TSV "
            "row per node to ~/.scitex/dev/runtime/spartan-conn-monitor.tsv; "
            "audio-notify + PHONE-CALL the operator if ssh-agents>15, srun>50, "
            "or procs>250 (early warning before the HPC admin notices). See "
            "_spartan_conn_monitor.run_once."
        ),
    ),
    "creds-rotate-all": JobSpec(
        name="creds-rotate-all",
        # Top of every hour. Matches the operator's pre-existing ad-hoc
        # `# scitex-dev creds-rotate (managed)` crontab line (the
        # default `creds rotate-all` install cadence, see
        # `_creds._cron._interval_to_schedule(60)` => "0 * * * *") that
        # this entry federates into the managed block.
        schedule="0 * * * *",
        command=_creds_rotate_all_command(),
        description=(
            "Push the freshest local ~/.claude/.credentials.json to every "
            "managed ecosystem checkout via `scitex-dev creds rotate-all "
            "--yes`. Federates the ad-hoc host line "
            "(# scitex-dev creds-rotate (managed)) into the managed block; "
            "keeps that line's 1-MiB log-rotation guard and writes to "
            "~/.scitex/dev/logs/creds-rotate.log. See _creds._cron / "
            "_creds._rotate."
        ),
    ),
    "ci-runner-ensure": JobSpec(
        name="ci-runner-ensure",
        # Every 30 minutes. Federates the operator's ad-hoc
        # ci-runner-ensure crontab line; the body is the standalone host
        # script ~/.scitex/dev/ci-runner-ensure-cron.sh (already
        # deployed). Schedule mirrors the retired ad-hoc line exactly.
        schedule="*/30 * * * *",
        command=_ci_runner_ensure_command(),
        description=(
            "Ensure the self-hosted GitHub Actions runners are present & "
            "alive by running ~/.scitex/dev/ci-runner-ensure-cron.sh. "
            "Federates the ad-hoc host crontab line into the managed "
            "block. Log at ~/.scitex/dev/logs/ci-runner-ensure.log."
        ),
    ),
    "ci-runner-workgc": JobSpec(
        name="ci-runner-workgc",
        # Every 6 hours on the hour. Federates the operator's ad-hoc
        # ci-runner-workgc crontab line; the body is the standalone host
        # script ~/.scitex/dev/ci-runner-workgc-cron.sh (already
        # deployed). Schedule mirrors the retired ad-hoc line exactly.
        schedule="0 */6 * * *",
        command=_ci_runner_workgc_command(),
        description=(
            "Garbage-collect the self-hosted CI runners' _work/ staging "
            "trees by running ~/.scitex/dev/ci-runner-workgc-cron.sh. "
            "Federates the ad-hoc host crontab line into the managed "
            "block. Log at ~/.scitex/dev/logs/ci-runner-workgc.log."
        ),
    ),
    "ecosystem-sync": JobSpec(
        name="ecosystem-sync",
        # Top of every hour. A git fetch of an already-current checkout is
        # a couple KB and the ff-merge only runs when actually behind, so
        # hourly is cheap even across ~60 repos while bounding drift to
        # <=1h. Tunable: change THIS schedule (one diff + one test) and
        # re-install. See _ecosystem_sync_command for why it exists.
        schedule="0 * * * *",
        command=_ecosystem_sync_command(),
        description=(
            "Fast-forward every editable ecosystem checkout's develop to "
            "origin (self-pull) via `scitex-dev ecosystem sync --yes`. "
            "ff-only, develop-only, skips dirty/off-develop/diverged so "
            "un-pushed work is never clobbered. Closes the drift loop that "
            "let checkouts silently serve stale code (the workstation's own "
            "scitex-dev was 18 commits behind v0.21.0; the Spartan runner "
            "145 behind). Log at ~/.scitex/dev/logs/cron-ecosystem-sync.log."
        ),
    ),
    # Future entries land here. Suggested naming pattern: short
    # action-noun like `rotate-all`, `audit-sweep`, `pypi-publish-watch`.
}


def get_job(name: str) -> JobSpec:
    """Return the registered ``JobSpec`` for ``name`` or raise KeyError."""
    try:
        return JOB_REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(JOB_REGISTRY)) or "(none)"
        raise KeyError(f"unknown cron job: {name!r}. Known jobs: {known}") from None


def list_jobs() -> list[JobSpec]:
    """Return every registered ``JobSpec`` sorted by name."""
    return [JOB_REGISTRY[k] for k in sorted(JOB_REGISTRY)]


# EOF
