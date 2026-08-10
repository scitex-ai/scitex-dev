#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron exec <name>`` — execute a managed job's body.

This is the entry point the materialised crontab line invokes. Since the
2026-07-19 cron cleanup it also OWNS the job's logging: it creates the
log directory, rotates the log when oversized, and redirects stdout +
stderr into it, so the crontab line reduces to::

    */10 * * * * scitex-dev cron exec ci-watch # scitex-dev cron: ci-watch

The plumbing itself is the shared, package-generic
``scitex_dev.jobs._logsink`` helper — deliberately NOT inlined here, so
it stays callable unchanged when these jobs migrate onto the federated
``jobs.JobSpec`` (card dev-two-jobspec-classes-ssot-violation-20260719).

FAIL LOUD: if the log dir cannot be created or the log cannot be opened,
the job does NOT run unlogged — it exits non-zero with the reason on
stderr. A cron job whose logging silently stopped is indistinguishable
from one that ran fine.

Verb choice: ``exec`` rather than ``run`` because the CLI audit (§1c)
intentionally treats ``run`` as a noun-only token — the canonical verbs
for "execute this thing" are ``exec`` / ``execute`` / ``start-run``.
"""

from __future__ import annotations

import subprocess

import click

from . import (
    _branch_gc,
    _ci_watch,
    _cred_distribute,
    _quota_keepalive,
    _spartan_conn_monitor,
    _task_harvest,
    _worktree_gc,
)
from ._job_commands import JOB_SHELL_BODIES, log_path_for
from ._jobs import JOB_REGISTRY
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ...jobs._logsink import LogSinkError, redirect_to_log


def _run_body(name: str, *, only: str | None, dry_run: bool) -> int:
    """Run job ``name``'s body. Returns the process exit code.

    Split out from the Click callback so the log-sink wrapper stays a
    single ``with`` block around ONE call, rather than being threaded
    through every dispatch branch.
    """
    if name in JOB_SHELL_BODIES:
        # Shell-payload job (host script / console-script pipeline). The
        # body is a PURE payload — no mkdir, no redirect, no rotation;
        # this function's caller already supplied all three. Inherits
        # fds 1/2, which the log sink has redirected at the fd level, so
        # subprocess output is captured too.
        completed = subprocess.run(JOB_SHELL_BODIES[name], shell=True, check=False)
        return completed.returncode

    if name == "ci-watch":
        results = _ci_watch.run_once(only_agent=only, dry_run=dry_run)
        # Don't crash the cron loop on a transient gh hiccup — just exit
        # non-zero so the log records the failure.
        return 1 if any(r.error is not None for r in results) else 0

    if name == "quota-keepalive":
        # Self-gating keepalive — fires only when the 2.5-hour interval
        # has elapsed. A keepalive miss is recoverable (the next 30-min
        # tick retries), so we always exit 0: the log records any error
        # but the cron loop must not be marked failed for a transient
        # `claude` hiccup.
        _quota_keepalive.run_once()
        return 0

    if name == "worktree-gc":
        # Best-effort cleanup loop — a per-worktree git error must not
        # crash the cron. We exit non-zero only if the WHOLE pass failed
        # (no roots discoverable, etc.) so a clean log distinguishes
        # "ran, removed N, refused M" from "couldn't run at all".
        return 1 if _worktree_gc.run_once(dry_run=dry_run).error is not None else 0

    if name == "branch-gc":
        # Config-gated (DEFAULT OFF) branch hygiene. Exit non-zero ONLY
        # when the WHOLE pass failed to run — a repo that is merely off,
        # aborted, or unreadable is reported in the log and does not fail
        # the cron loop, matching the worktree-gc branch's policy. The
        # `--dry-run` flag forces report-only even for armed repos so an
        # operator can preview a pass by hand.
        return 1 if _branch_gc.run_once(dry_run=dry_run).failed else 0

    if name == "task-harvest":
        # Best-effort classification + audit log of the shared
        # ~/.scitex/todo/tasks.yaml board. A missing/malformed store sets
        # ``result.error`` and exits non-zero so the log records the
        # failure, but the cron loop keeps ticking.
        return 1 if _task_harvest.run_once().error is not None else 0

    if name == "cred-distribute":
        # Exit-code policy:
        #   - config malformed / bootstrap failed -> 1 (pages the operator)
        #   - every attempted host failed -> 1 (systemic outage signal);
        #     one host failing while another succeeded is a transient
        #     hiccup, not a page.
        #   - sac binary / subcommand missing -> 0 (graceful rollout
        #     window; the body marks those hosts skipped).
        #   - all-skipped -> 0; the audit line records the no-op.
        result = _cred_distribute.run_once()
        if result.error is not None or result.all_attempted_failed:
            return 1
        return 0

    if name == "spartan-conn-monitor":
        # The body logs a TSV row per node and phones the operator on a
        # threshold breach. An unreachable node or notification hiccup is
        # swallowed (cron-safe); we exit non-zero ONLY when a threshold
        # was actually crossed, so the log + cron mail flag a real
        # regression.
        return 1 if _spartan_conn_monitor.run_once().alerts else 0

    # Defensive — registry has an entry but no handler. Reaching here
    # means someone added a `JOB_REGISTRY` entry without wiring its
    # run-body. Fail loudly per the no-silent-stubs rule.
    raise click.ClickException(
        f"cron job {name!r} is registered but has no `exec` handler. "
        f"Add a dispatch branch in `_cli/cron/run.py` or a shell body in "
        f"`_job_commands.JOB_SHELL_BODIES`."
    )


def register(group: click.Group) -> None:
    @group.command(
        "exec",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Execute the body of the managed job NAME.",
            description=(
                "This is the verb the materialised crontab line invokes. "
                "It owns its own logging: the log directory is created, "
                "the log is rotated when it exceeds 1 MiB, and stdout + "
                "stderr are redirected into "
                "$HOME/.scitex/<pkg>/runtime/logs/<slug>.log — so the "
                "crontab line carries a schedule and a command and "
                "nothing else. Operators can also run it interactively "
                "to test a job; pass --no-log to keep output on the "
                "terminal.",
            ),
            examples=(
                Example("{prog} cron exec ci-watch", "Run the job, logging to file."),
                Example(
                    "{prog} cron exec ci-watch --no-log",
                    "Run it with output on the terminal.",
                ),
                Example(
                    "{prog} cron exec ci-watch --only proj-scitex-stats --dry-run --no-log",
                    "Preview for one agent, on the terminal.",
                ),
            ),
        ),
    )
    @click.argument("name")
    @click.option(
        "--only",
        "only",
        default=None,
        help="(ci-watch) Restrict the pass to a single agent name.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="(ci-watch) Print the prompt that would be dispatched without "
        "calling `sac agents send`.",
    )
    @click.option(
        "--no-log",
        "no_log",
        is_flag=True,
        default=False,
        help="Write output to the terminal instead of the job's log file. "
        "For interactive testing — cron always wants the default.",
    )
    def exec_cmd(name: str, only: str | None, dry_run: bool, no_log: bool) -> None:
        if name not in JOB_REGISTRY:
            known = ", ".join(sorted(JOB_REGISTRY)) or "(none)"
            raise click.ClickException(
                f"unknown cron job: {name!r}. Known jobs: {known}"
            )

        if no_log:
            code = _run_body(name, only=only, dry_run=dry_run)
            if code:
                raise SystemExit(code)
            return

        log = log_path_for(name)
        try:
            # `redirect_to_log` prepares the sink on ENTER, so the
            # `with` must be inside the guard — a LogSinkError raised by
            # mkdir/rotate/open surfaces here rather than killing the
            # job with an unhandled traceback.
            with redirect_to_log(log):
                code = _run_body(name, only=only, dry_run=dry_run)
        except LogSinkError as exc:
            # FAIL LOUD. Never degrade to unlogged execution: a cron job
            # whose logging silently stopped looks exactly like one that
            # ran fine.
            raise click.ClickException(str(exc)) from exc

        if code:
            # Raised OUTSIDE the redirect so the operator sees which job
            # failed on stderr / in cron mail, not only inside the log.
            raise SystemExit(code)


# EOF
