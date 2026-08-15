#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Per-job crontab-line builders + log targets for the managed registry.

THE CRONTAB LINE CARRIES SCHEDULE + COMMAND, NOTHING ELSE
---------------------------------------------------------
Every builder here now returns the bare console-script invocation::

    scitex-dev cron exec <name>

so the materialised crontab line reads::

    */10 * * * * scitex-dev cron exec ci-watch # scitex-dev cron: ci-watch

The ``mkdir -p``, the ``>> <log> 2>&1`` redirect, and the 1-MiB rotation
guard that used to be inlined into each line are OWNED BY THE VERB — see
``scitex_dev.jobs._logsink`` (the shared, package-generic helper) and the
``cron exec`` dispatcher in ``run.py`` that applies it. Operator
directive 2026-07-19: 「mkdir とか redirect は cron verb 側が持つべきでは？」
— shouldn't the mkdir and the redirect be owned by the cron verb?

WHERE THE LOGS GO
-----------------
``JOB_LOG_TARGETS`` maps each job to ``(package, slug)``, resolved by
``_logsink.log_path`` to::

    $HOME/.scitex/<package>/runtime/logs/<slug>.log

All scitex-dev-owned jobs use package ``dev`` — under ``runtime/``, per
the operator directive already recorded in ``jobs/_respawn.py``:26. The
previous ``~/.scitex/dev/logs/`` location violated it. Existing logs at
the old path are NOT moved; new writes go to the new path and
``cron status`` falls back to the legacy path so nothing goes dark
during the transition.

SHELL-BODY JOBS
---------------
Five jobs are not Python bodies but shell pipelines (host scripts,
``creds rotate-all``, the scholar rsync). Their bodies live in
``JOB_SHELL_BODIES`` as PURE payloads — no mkdir, no redirect, no
rotation — and ``cron exec`` runs them under the same log sink as the
Python jobs. That is what lets every job, not just the Python ones,
reduce to ``scitex-dev cron exec <name>`` in the crontab.

Generated shell text uses ``$HOME``, never ``~``: ``~`` is expanded only
by an interactive shell in command position, and cron's ``/bin/sh -c``
context does not reliably expand it (operator directive 2026-07-19:
「~ が解決されないならば $HOME を使って」 — if ``~`` is not resolved,
use ``$HOME``).
"""

from __future__ import annotations

from pathlib import Path

from ...jobs import _logsink

#: The package that owns scitex-dev's own cron logs. These are
#: scitex-dev's OWN jobs, so ``dev`` is the correct owning package —
#: this is not about hoarding other leaves' logs. ``scholar-library-sync``
#: is the one job that logs under a different leaf (it syncs scholar
#: state, so its log lives with that state).
DEFAULT_LOG_PACKAGE = "dev"

#: name -> (owning package, log basename without ``.log``).
#: Jobs absent from this map fall back to ``(DEFAULT_LOG_PACKAGE,
#: f"cron-{name}")`` via :func:`log_target_for`.
JOB_LOG_TARGETS: dict[str, tuple[str, str]] = {
    # NOTE the slug is ``creds-rotate`` (NO ``cron-`` prefix): the ad-hoc
    # host line this entry federated wrote to exactly that basename, and
    # operators / dashboards that tail it must keep working.
    "creds-rotate-all": (DEFAULT_LOG_PACKAGE, "creds-rotate"),
    "ci-runner-ensure": (DEFAULT_LOG_PACKAGE, "ci-runner-ensure"),
    "ci-runner-workgc": (DEFAULT_LOG_PACKAGE, "ci-runner-workgc"),
    # The scholar library sync moves SCHOLAR state, so its log lives in
    # the scholar leaf's runtime tree (2026-07-01 operator directive).
    "scholar-library-sync": ("scholar", "cron-library-sync"),
}


def log_target_for(name: str) -> tuple[str, str]:
    """Return ``(package, slug)`` for job ``name``."""
    return JOB_LOG_TARGETS.get(name, (DEFAULT_LOG_PACKAGE, f"cron-{name}"))


def log_path_for(name: str, *, home: Path | None = None) -> Path:
    """Return the resolved ``runtime/logs`` path for job ``name``.

    Delegates to the shared :mod:`scitex_dev.jobs._logsink` helper so the
    path convention has exactly one implementation and stays correct once
    these jobs migrate onto the federated ``jobs.JobSpec``.
    """
    package, slug = log_target_for(name)
    return _logsink.log_path(package, slug, home=home)


def exec_command(name: str) -> str:
    """Return the crontab command body for job ``name``.

    Schedule + command + marker is the WHOLE line; the verb owns its own
    log dir, redirect and rotation.
    """
    return f"scitex-dev cron exec {name}"


# ---------------------------------------------------------------------
# Per-job builders. Each is a thin `exec_command(<name>)` now that the
# plumbing moved into the verb; they are kept as named functions because
# ``_jobs`` re-exports them and tests pin the registry through them.
# ---------------------------------------------------------------------


def _ci_watch_command() -> str:
    """The shell line installed for the ``ci-watch`` cron job.

    We invoke the console script so the line stays stable across
    virtual-env shuffles — ``scitex-dev`` is on PATH wherever this CLI is
    installed. Output lands in
    ``$HOME/.scitex/dev/runtime/logs/cron-ci-watch.log``.
    """
    return exec_command("ci-watch")


def _worktree_gc_command() -> str:
    """The shell line installed for the ``worktree-gc`` cron job.

    Schedule rationale: every 6 hours is conservative — a single sweep is
    short (find git dirs, ``git worktree list``, mtime check), and
    proj-scitex-agent-container is concurrently working on the RELOCATION
    half (stopping ``.claude/worktrees`` from being created in the first
    place), so the cleanup loop's load will fall over time.
    """
    return exec_command("worktree-gc")


def _branch_gc_command() -> str:
    """The shell line installed for the ``branch-gc`` cron job.

    Schedule rationale: daily at 04:00, off the crowded 0-minute tick. A
    sweep is cheap (one ``for-each-ref`` plus a bounded set of per-branch
    git reads), and the default age floor is 30 days with a hard floor of
    14 — so nothing is gained by running it more often than daily and a
    slower cadence would only widen the window in which a landed branch
    sits around.

    The body is ``_branch_gc.run_once``. Installing this job does NOT arm
    it: every repo stays DEFAULT OFF until ``cleanup.branches.enabled:
    true`` appears in both ``<repo>/.scitex/dev/config.yaml`` and
    ``$HOME/.scitex/dev/config.yaml``.
    """
    return exec_command("branch-gc")


def _quota_keepalive_command() -> str:
    """The shell line installed for the ``quota-keepalive`` cron job.

    The crontab schedule is ``*/30 * * * *`` (every 30 minutes), but the
    body self-gates to fire only every 2.5 hours — see
    ``_quota_keepalive.run_once`` for why 2.5 h cannot be one cron
    interval and how the timestamp gate enforces exact spacing.
    """
    return exec_command("quota-keepalive")


def _cred_distribute_command() -> str:
    """The shell line installed for the ``cred-distribute`` cron job.

    Schedule rationale: every 2 hours (``0 */2 * * *``) — matches the
    operator's pre-existing ad-hoc ``spartan-cred-push`` cadence and is
    conservative for credentials that turn over on a multi-hour window.

    Body lives in ``_cred_distribute.run_once``; the per-host list and
    credential selector are read from
    ``$HOME/.scitex/dev/cred-distribute.yaml`` so switching behaviour
    does not require any code change.
    """
    return exec_command("cred-distribute")


def _task_harvest_command() -> str:
    """The shell line installed for the ``task-harvest`` cron job.

    Schedule rationale: every 6 hours (``0 */6 * * *``) — 4 sweeps per
    day keeps consumption-rate pressure on the board without spamming
    agent inboxes. Body lives in ``_task_harvest.run_once``; the
    operator-facing PROTOCOL lives in
    ``scitex_todo._skills.scitex-todo.40_task-harvest``.
    """
    return exec_command("task-harvest")


def _spartan_conn_monitor_command() -> str:
    """The shell line installed for the ``spartan-conn-monitor`` cron job.

    Schedule ``*/30 * * * *`` — light (one multiplexed ssh + pgrep/ps/who
    per login node), enough to catch a connection/agent regression long
    before the HPC admin would. Body in
    ``_spartan_conn_monitor.run_once``; metrics history is the TSV at
    ``$HOME/.scitex/dev/runtime/spartan-conn-monitor.tsv``.
    """
    return exec_command("spartan-conn-monitor")


def _creds_rotate_all_command() -> str:
    """The shell line installed for the ``creds-rotate-all`` cron job.

    Federates the operator's pre-existing ad-hoc crontab line (tagged
    ``# scitex-dev creds-rotate (managed)`` — see ``_creds._cron``) into
    the managed registry. The 1-MiB log-rotation guard that line carried
    inline is now applied by the verb to EVERY job (``_logsink``), not
    just this one.
    """
    return exec_command("creds-rotate-all")


def _ci_runner_ensure_command() -> str:
    """The shell line installed for the ``ci-runner-ensure`` cron job.

    The job body is the standalone host script
    ``$HOME/.scitex/dev/ci-runner-ensure-cron.sh`` (already deployed on
    the host); see ``JOB_SHELL_BODIES``.
    """
    return exec_command("ci-runner-ensure")


def _ci_runner_workgc_command() -> str:
    """The shell line installed for the ``ci-runner-workgc`` cron job.

    The job body is the standalone host script
    ``$HOME/.scitex/dev/ci-runner-workgc-cron.sh`` (already deployed on
    the host); see ``JOB_SHELL_BODIES``.
    """
    return exec_command("ci-runner-workgc")


def _ecosystem_sync_command() -> str:
    """The shell line installed for the ``ecosystem-sync`` cron job.

    Runs the WRITE self-pull ``scitex-dev ecosystem sync --yes``, which
    fast-forwards every editable checkout's ``develop`` to
    ``origin/develop``. Safe by construction: develop-only,
    ``git merge --ff-only``, and dirty / off-develop / diverged checkouts
    are reported and SKIPPED — never clobbered.

    Why this is a MANAGED job: the ecosystem runs on editable installs
    that import their own working tree, but ``origin/develop`` advances
    on its own. Without a periodic self-pull a checkout silently serves
    stale code — the workstation's own ``scitex-dev`` checkout was found
    18 commits behind tag v0.21.0 (2026-07-01) and the Spartan runner
    145 behind.
    """
    return exec_command("ecosystem-sync")


def _scholar_library_sync_command() -> str:
    """The shell line installed for the ``scholar-library-sync`` cron job.

    One-way rsync of the scholar library, host-WSL -> Spartan, via
    ``scitex-ssh sync``. Design locked with scitex-scholar + scitex-ssh
    (card scholar-library-cross-machine-sync-20260701); the pipeline
    itself lives in ``JOB_SHELL_BODIES``:

    - WSL is the AUTHORITY; the push is one-way and ``--delete`` is never
      passed, so a Spartan-side mistake cannot propagate back.
    - ``index.db`` + journal/WAL/SHM siblings are EXCLUDED: the index is
      DERIVED state, rebuilt on the destination after each push —
      shipping a live SQLite file mid-write corrupts it.
    - ``ssh spartan mkdir -p`` precedes the rsync because Spartan's
      system rsync predates 3.2.3 (no ``--mkpath``).
    - A failed rsync short-circuits the rebuild (``&&``) so a partial
      tree is never indexed.
    - PRE-SYNC DEDUPE on the authority side quarantines duplicate-DOI
      losers to ``MASTER_quarantine/`` (reversible, never hard-deletes).

    Requires ``scitex-ssh`` (>=1.1.0) + ``scitex-scholar`` (>=1.4.3) —
    both in the ``[sync]`` extra — and ``rsync`` on the host.
    """
    return exec_command("scholar-library-sync")


# ---------------------------------------------------------------------
# Shell payloads for the jobs whose body is not a Python entry point.
# PURE bodies: no mkdir, no redirect, no rotation — `cron exec` supplies
# all three via the shared log sink.
# ---------------------------------------------------------------------

_SCHOLAR_LIB = "$HOME/.scitex/scholar/library"
_SCHOLAR_EXCLUDES = (
    "--exclude index.db --exclude index.db-journal "
    "--exclude index.db-wal --exclude index.db-shm"
)

JOB_SHELL_BODIES: dict[str, str] = {
    "creds-rotate-all": "scitex-dev creds rotate-all --yes",
    "ci-runner-ensure": "$HOME/.scitex/dev/ci-runner-ensure-cron.sh",
    "ci-runner-workgc": "$HOME/.scitex/dev/ci-runner-workgc-cron.sh",
    "ecosystem-sync": "scitex-dev ecosystem sync --yes",
    "scholar-library-sync": (
        f"scitex-scholar library dedupe --apply --library-root {_SCHOLAR_LIB} && "
        "ssh spartan 'mkdir -p $HOME/.scitex/scholar/library' && "
        f"scitex-ssh sync {_SCHOLAR_LIB}/ spartan:.scitex/scholar/library/ "
        f"{_SCHOLAR_EXCLUDES} --yes && "
        "ssh spartan 'bash -lc \"scitex-scholar library db build "
        "--library-root $HOME/.scitex/scholar/library\"'"
    ),
}


# EOF
