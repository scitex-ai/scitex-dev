#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scitex-dev's own provider for the ``scitex_dev.jobs`` federation.

scitex-dev applies the dual-mode principle to itself: every other
leaf in the ecosystem registers a ``scitex_dev.jobs`` entry-point that
``scitex-dev ecosystem cron install`` discovers and materialises;
scitex-dev does the same for the JOBS IT ITSELF OWNS at the ECOSYSTEM
LEVEL (jobs that operate across packages, not within a single one).

scitex-dev's OWN, package-internal crons (ci-watch, quota-keepalive,
worktree-gc, task-harvest, cred-distribute) stay under
``scitex-dev cron`` — that's the standalone surface for scitex-dev as
a package. The cross-package control-plane jobs declared here flow
through ``scitex-dev ecosystem cron`` via the federation, alongside
every other leaf's contributions.

Today's roster
--------------
- ``deploy-freshness`` — detects (and with ``--apply`` repairs) drift
  between the installed and latest released version of every
  kind=service / kind=timer JobSpec discovered through the
  federation. See ``_deploy_freshness.run_once``.
"""

from __future__ import annotations

from scitex_dev.jobs import JobSpec


def _deploy_freshness_command() -> str:
    """Shell line installed for the ``deploy-freshness`` ecosystem cron job."""
    log = "$HOME/.scitex/dev/logs/cron-deploy-freshness.log"
    return (
        f"mkdir -p $(dirname {log}); "
        f"scitex-dev ecosystem cron exec deploy-freshness --apply "
        f">> {log} 2>&1"
    )


def provide_jobs() -> list[JobSpec]:
    """Return scitex-dev's ecosystem-level JobSpecs for the federation.

    Loaded by ``scitex_dev.jobs.discover_jobs()`` through the
    ``scitex_dev.jobs`` entry-point group — scitex-dev's own
    pyproject.toml declares this provider just like any other leaf.
    """
    return [
        JobSpec(
            name="deploy-freshness",
            kind="cron",
            schedule="*/30 * * * *",
            command=_deploy_freshness_command(),
            description=(
                "Detect & repair drift between installed and latest "
                "released versions of every managed service/timer "
                "JobSpec. Compares importlib.metadata version against "
                "PyPI; with --apply runs `pip install -U <pkg>` + "
                "`systemctl --user restart <unit>` per drifted leaf. "
                "Audit log at ~/.scitex/dev/logs/cron-deploy-freshness.log. "
                "See _ecosystem_jobs._deploy_freshness.run_once."
            ),
        ),
    ]


# EOF
