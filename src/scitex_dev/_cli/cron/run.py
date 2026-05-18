#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cron exec <name>`` — execute a managed job's body.

This is the entry point the materialised crontab line invokes — it
delegates to the job-specific implementation module (e.g.
``_ci_watch.run_once`` for ``ci-watch``). Adding a new job means
implementing its exec-body here in addition to registering it in
``_jobs.JOB_REGISTRY``.

Verb choice: ``exec`` rather than ``run`` because the CLI audit (§1c)
intentionally treats ``run`` as a noun-only token — the canonical
verbs for "execute this thing" are ``exec`` / ``execute`` / ``start-run``.
"""

from __future__ import annotations

import click

from . import _ci_watch
from ._jobs import JOB_REGISTRY


def register(group: click.Group) -> None:
    @group.command("exec")
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
    def exec_cmd(name: str, only: str | None, dry_run: bool) -> None:
        """Execute the body of the managed job NAME.

        \b
        This is the verb the materialised crontab line invokes — operators
        can also run it interactively to test a job without waiting for
        the next cron tick.

        \b
        Example:
          $ scitex-dev cron exec ci-watch
          $ scitex-dev cron exec ci-watch --dry-run
          $ scitex-dev cron exec ci-watch --only proj-scitex-stats --dry-run
        """
        if name not in JOB_REGISTRY:
            known = ", ".join(sorted(JOB_REGISTRY)) or "(none)"
            raise click.ClickException(
                f"unknown cron job: {name!r}. Known jobs: {known}"
            )

        if name == "ci-watch":
            results = _ci_watch.run_once(
                only_agent=only,
                dry_run=dry_run,
            )
            errors = sum(1 for r in results if r.error is not None)
            if errors:
                # Don't crash the cron loop on a transient gh hiccup —
                # just exit non-zero so the log records the failure.
                raise SystemExit(1)
            return

        # Defensive — registry has an entry but no handler. Reaching here
        # means someone added a `JOB_REGISTRY` entry without wiring its
        # run-body. Fail loudly per the no-silent-stubs rule.
        raise click.ClickException(
            f"cron job {name!r} is registered but has no `exec` handler. "
            f"Add a dispatch branch in `_cli/cron/run.py`."
        )


# EOF
