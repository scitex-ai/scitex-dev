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
  in every kind=service / kind=timer JobSpec discovered through the
  federation, on two axes: WHEEL drift (installed version trails the
  latest PyPI release → ``pip install -U`` + restart) and EDITABLE
  drift (a PEP 660 editable install whose git source is newer than the
  unit's last start → restart only, no pip). See
  ``_deploy_freshness.run_once``.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev.jobs import JobSpec

# ---------------------------------------------------------------------------
# The federated cron/timer VERB owns logging, exactly as the built-in
# ``scitex-dev cron exec`` does since #367 (see ``jobs/_respawn.py``:25-27
# for the operator directive). Every job below reduces to the bare verb
# ``scitex-dev ecosystem cron exec <name>``; the ``cron exec`` dispatcher
# in ``_cli.ecosystem._cmds._jobs_cron`` wraps the body in
# ``jobs._logsink.redirect_to_log`` so mkdir + rotation + the fd-level
# (``os.dup2``) redirect all live in ONE place and land under
#
#     $HOME/.scitex/<package>/runtime/logs/<slug>.log
#
# never ``$HOME/.scitex/dev/logs/`` (the pre-#367 location this file used,
# which violated the directive). Routing timers through the verb also FIXES
# a latent bug: a systemd ``ExecStart`` is exec'd, not shell-parsed, so the
# old inline ``mkdir …; cmd >> log 2>&1`` string was mangled by
# ``resolve_execstart``'s ``shlex.split`` (junk args to ``/bin/mkdir``). A
# single console-script invocation resolves cleanly.
#
# ``JOB_LOG_TARGETS`` maps each job to ``(package, slug)``; the slug keeps
# the pre-existing log basename so operator greps / dashboards keep working.
JOB_LOG_TARGETS: dict[str, tuple[str, str]] = {
    "scitex-dev-deploy-freshness": ("dev", "cron-deploy-freshness"),
    "scitex-dev-pr-expire": ("dev", "cron-pr-expire"),
    "scitex-dev-ecosystem-self-pull": ("dev", "timer-ecosystem-self-pull"),
    "scitex-dev-drift-report": ("dev", "timer-drift-report"),
    "scitex-dev-local-state-audit": ("dev", "timer-local-state-audit"),
    "scitex-dev-host-config-check": ("dev", "timer-host-config-check"),
    "scitex-dev-venv-refresh": ("dev", "timer-venv-refresh"),
}

#: Pure shell bodies for the jobs whose body is not a Python entry point —
#: no mkdir, no redirect, no rotation; ``cron exec`` supplies all three via
#: the shared log sink (mirrors ``_cli.cron._job_commands.JOB_SHELL_BODIES``).
#: ``deploy-freshness`` is absent — it dispatches to ``_deploy_freshness.
#: run_once`` in Python, not a shell body. The ``|| true`` on the OBSERVE
#: jobs keeps a drift FINDING from marking the unit failed (drift is data
#: recorded in the log, not a unit failure — skill §4).
JOB_SHELL_BODIES: dict[str, str] = {
    "scitex-dev-pr-expire": (
        "date -u +'== pr-expire %Y-%m-%dT%H:%MZ =='; "
        # flip to --apply after fleet-wide dry-run validation — constitution
        # §2, do not auto-mass-close 12 repos on first fire.
        "scitex-dev ecosystem pr expire --all --days 3 --dry-run || true"
    ),
    "scitex-dev-ecosystem-self-pull": "scitex-dev ecosystem sync --yes",
    "scitex-dev-drift-report": (
        "date -u +'== drift-report %Y-%m-%dT%H:%MZ =='; "
        "scitex-dev ecosystem drift-report || true"
    ),
    "scitex-dev-local-state-audit": (
        "date -u +'== local-state-audit %Y-%m-%dT%H:%MZ =='; "
        "scitex-dev ecosystem audit-local-state || true"
    ),
    # The shared dev venv, kept current. `--venv current` means "the
    # interpreter this job runs under", so the unit's ExecStart decides which
    # venv is refreshed — the job carries no hardcoded path.
    #
    # `-U` is ON here and OFF for interactive `ecosystem install`, on purpose:
    # currency IS the product of this job, whereas an interactive install
    # should not silently move a dependency under whatever the caller was
    # editing.
    #
    # `|| true` because a refresh finding — one leaf whose [all] extra does
    # not resolve — is DATA in the log, not this unit failing. Measured
    # 2026-08-17: `scitex[all]` pulls 34 of the ecosystem's scitex-* packages,
    # misses 11 that are checked out, and still pins scitex-orochi (retired)
    # and scitex-dev==0.28.0 against an actual 0.51.0. A job that goes red on
    # that is a job someone disables.
    #
    # NOT a substitute for per-package venvs. A shared env has every peer
    # installed, so a MISSING dependency declaration is invisible in it by
    # construction; `--venv per-package` (the default, and what CI uses) is
    # the only thing that can see that class of defect.
    # TWO PASSES, and the second is not optional. Pass 1 may re-resolve, so
    # a later package's dependency on a sibling can replace that sibling's
    # editable install with a PyPI wheel; pass 2 (--no-deps) cannot resolve
    # anything, so it re-asserts every checkout as editable and nothing it
    # touches can clobber a peer. Measured 2026-08-17: pass 1 alone reported
    # ok=22 fail=0 and left three packages resolving to site-packages.
    # TWO POPULATIONS, BOTH REFRESHED, NEITHER ALLOWED TO FAIL QUIETLY.
    #
    # This job used to pass `--venv current` for both passes. `current` is the
    # OPT-IN mode — `install --help` says to use it "only when you
    # intentionally want every peer installed into the same env" — and it means
    # "the interpreter this job runs under", so the unit's ExecStart decided
    # which single venv got refreshed and every OTHER venv on the host was
    # refreshed by nobody.
    #
    # MEASURED on ywata-note-win 2026-08-19: the job had run three times that
    # day, exit 0 every time, while ~/proj/scitex-agent-container/.venv sat on
    # scitex-dev 0.49.2.dev103 and ~/.venv on 0.55.0. The operator brought his
    # own venv current BY HAND (`uv pip install -Ue`, 56 packages moved) and
    # asked why the automatic update had not. This is why.
    #
    # OPERATOR RULE, 2026-08-19, stated as global: "cd ~/proj/xxx && source
    # .venv/bin/activate && uv pip install -Ue .[all] must be done
    # periodically; especially when the package updated ... in any place in
    # any host", and "they must have self-update system turned on in our case
    # especially for the ones with EDITABLE installation". An editable install
    # tracks a moving checkout, so its DEPENDENCIES go stale even while the
    # package itself is current — which is exactly the 56-package gap above.
    #
    # `--venv per-package` is the DEFAULT of `ecosystem install` and creates /
    # refreshes ~/proj/<pkg>/.venv for every package. Pass 3 keeps the shared
    # runtime venv current too, because agents execute from it.
    #
    # NO `|| true` HERE. The observe-jobs use it so a drift FINDING does not
    # mark the unit failed; this job does not observe, it INSTALLS, and a
    # failed install is a failure. With `|| true` the unit reported success
    # three times while refreshing a venv nobody uses — a gate that cannot
    # fail is not a gate. `set -e` makes the first failing pass stop the job
    # loudly, which is the whole point of running it.
    "scitex-dev-venv-refresh": (
        "set -e; "
        "date -u +'== venv-refresh %Y-%m-%dT%H:%MZ =='; "
        "echo '-- pass 1/3: every ~/proj/<pkg>/.venv, with deps --'; "
        "scitex-dev ecosystem install --source editable --extras all "
        "--venv per-package --upgrade --yes; "
        "echo '-- pass 2/3: re-asserting editables (--no-deps) --'; "
        "scitex-dev ecosystem install --source editable "
        "--venv per-package --no-deps --yes; "
        "echo '-- pass 3/3: the shared runtime venv agents execute from --'; "
        "scitex-dev ecosystem install --source editable --extras all "
        "--venv current --upgrade --yes"
    ),
    # OBSERVE-only by construction: `host-config check` never writes, and
    # it needs no privileges (the managed files under /etc are
    # world-readable), so the unprivileged periodic job can report drift
    # honestly. Converging is `host-config apply`, a deliberate root act
    # — a timer must never quietly rewrite a host's /etc.
    "scitex-dev-host-config-check": (
        "date -u +'== host-config-check %Y-%m-%dT%H:%MZ =='; "
        "scitex-dev ecosystem host-config check || true"
    ),
}


def log_target_for(name: str) -> tuple[str, str]:
    """Return ``(package, slug)`` for federated job ``name``."""
    return JOB_LOG_TARGETS.get(name, ("dev", f"cron-{name}"))


def log_path_for(name: str, *, home: Path | None = None) -> Path:
    """Return the resolved ``runtime/logs`` path for federated job ``name``.

    Delegates to the shared :mod:`scitex_dev.jobs._logsink` helper so the
    ``$HOME/.scitex/<pkg>/runtime/logs/<slug>.log`` convention has exactly
    one implementation across the built-in and federated cron surfaces.
    """
    from ..jobs import _logsink

    package, slug = log_target_for(name)
    return _logsink.log_path(package, slug, home=home)


def _exec_command(name: str, *, extra: str = "") -> str:
    """Return the bare ``ecosystem cron exec`` invocation for ``name``.

    Schedule + command + marker is the WHOLE crontab line / systemd
    ``ExecStart``; the verb owns its own log dir, redirect and rotation.
    """
    tail = f" {extra}" if extra else ""
    return f"scitex-dev ecosystem cron exec {name}{tail}"


def _deploy_freshness_command() -> str:
    """Command installed for the ``deploy-freshness`` ecosystem cron job.

    ``--apply`` is forwarded to the dispatcher (drift is REPAIRED, not just
    reported). Output lands in
    ``$HOME/.scitex/dev/runtime/logs/cron-deploy-freshness.log``.
    """
    return _exec_command("scitex-dev-deploy-freshness", extra="--apply")


def _self_pull_command() -> str:
    """Command installed for the ``ecosystem-self-pull`` timer.

    Runs the existing, non-destructive ``ecosystem sync`` sweep (see
    ``JOB_SHELL_BODIES``): per managed checkout it ff-merges
    ``origin/develop`` and skips anything dirty / off-develop / diverged,
    so live or un-pushed work is never clobbered.
    """
    return _exec_command("scitex-dev-ecosystem-self-pull")


def _drift_report_command() -> str:
    """Command installed for the ``drift-report`` timer.

    Runs the read-only ``ecosystem drift-report`` observe pass (see
    ``JOB_SHELL_BODIES``) and appends the full package × layer matrix to
    the runtime log. ``|| true`` keeps the OBSERVATION unit successful even
    when it FINDS drift: drift is data recorded in the report, not a unit
    failure — so a chronically-drifting fleet never trains the operator to
    ignore a permanently-failed timer (skill §4).
    """
    return _exec_command("scitex-dev-drift-report")


def _local_state_audit_command() -> str:
    """Command installed for the ``local-state-audit`` timer.

    Runs the read-only ``ecosystem audit-local-state`` observe pass across
    every registered package (see ``JOB_SHELL_BODIES``) and appends the
    findings + a greppable ``LOCAL-STATE-DRIFT: <N> ...`` summary to the
    runtime log. ``|| true`` keeps the OBSERVATION unit successful even
    when it FINDS drift (mirrors ``drift-report``). The
    ``check_state_drift.sh`` PostToolUse hook reads this log's last summary
    line.
    """
    return _exec_command("scitex-dev-local-state-audit")


def _venv_refresh_command() -> str:
    return _exec_command("scitex-dev-venv-refresh")


def _host_config_check_command() -> str:
    """Command installed for the ``host-config-check`` timer.

    Runs the read-only ``ecosystem host-config check`` pass (see
    ``JOB_SHELL_BODIES``): compares every ``scitex_dev.host_config``
    declaration against this host and appends the per-spec verdict to the
    runtime log AND to ``~/.scitex/dev/runtime/logs/host-config.log``.
    ``|| true`` keeps the OBSERVATION unit successful when it FINDS drift
    (mirrors ``drift-report`` / ``local-state-audit``) — `check` exits 1
    on drift by design, which is right for a human at a prompt and wrong
    for a timer, where a permanently-red unit trains the operator to
    ignore it.
    """
    return _exec_command("scitex-dev-host-config-check")


def _pr_expire_command() -> str:
    """Command installed for the ``pr-expire`` daily cron job.

    SAFETY — SHIPS IN --dry-run (REPORT) MODE, NOT --apply (see
    ``JOB_SHELL_BODIES``). The operator wants eventual fleet-wide
    auto-close, but a scheduled job that mass-closes 12 repos on its very
    first fire is exactly the kind of irreversible blast the constitution
    (§2) forbids. Flip ``--dry-run`` to ``--apply`` in ``JOB_SHELL_BODIES``
    ONLY after a fleet-wide dry-run has been validated by a human.
    """
    return _exec_command("scitex-dev-pr-expire")


def provide_jobs() -> list[JobSpec]:
    """Return scitex-dev's ecosystem-level JobSpecs for the federation.

    Loaded by ``scitex_dev.jobs.discover_jobs()`` through the
    ``scitex_dev.jobs`` entry-point group — scitex-dev's own
    pyproject.toml declares this provider just like any other leaf.
    """
    return [
        JobSpec(
            name="scitex-dev-deploy-freshness",
            kind="cron",
            schedule="*/30 * * * *",
            command=_deploy_freshness_command(),
            description=(
                "Detect & repair drift in every managed service/timer "
                "JobSpec, two axes. WHEEL: importlib.metadata version vs "
                "latest PyPI; with --apply runs `pip install -U <pkg>` + "
                "`systemctl --user restart <unit>`. EDITABLE (PEP 660): "
                "git source-commit time vs the unit's ActiveEnterTimestamp; "
                "with --apply runs `systemctl --user restart <unit>` only "
                "(no pip — source already in place; the pull stays the "
                "operator's deliberate act). Audit log at "
                "~/.scitex/dev/runtime/logs/cron-deploy-freshness.log. "
                "See _ecosystem_jobs._deploy_freshness.run_once."
            ),
        ),
        JobSpec(
            name="scitex-dev-ecosystem-self-pull",
            kind="timer",
            schedule="",
            command=_self_pull_command(),
            description=(
                "Keep every managed checkout's develop current "
                "(self-pull). Runs `scitex-dev ecosystem sync --yes` on a "
                "Persistent timer: OnBootSec catch-up after boot/reconcile + "
                "every ~2min. ff-only / develop-only / skips dirty+diverged, "
                "so un-pushed or live work is never clobbered. Closes the "
                "self-pull leg of the feedback loop (editable checkouts serve "
                "stale code until pulled). Log at "
                "~/.scitex/dev/runtime/logs/timer-ecosystem-self-pull.log. "
                "See _cli.ecosystem._cmds._sync."
            ),
            on_boot_sec="1min",
            on_unit_active_sec="2min",
        ),
        JobSpec(
            name="scitex-dev-drift-report",
            kind="timer",
            schedule="",
            command=_drift_report_command(),
            description=(
                "Unified version-drift observer. Runs `scitex-dev ecosystem "
                "drift-report` on a Persistent timer (OnBootSec catch-up + "
                "every 6h) and appends the package × layer matrix (PyPI / "
                "GitHub / per-host develop sha / container base-image + agent "
                "overlay via `sac versions --json` / editable-installed) to "
                "~/.scitex/dev/runtime/logs/timer-drift-report.log, so drift "
                "across "
                "hosts/containers/agents is caught in minutes, not discovered "
                "when something breaks (skill §5 north-star report). Read-only "
                "observe pass; the SSoT is pyproject@develop. Layers 5/6 "
                "degrade gracefully when sac is absent. See "
                "_ecosystem._drift_report."
            ),
            on_boot_sec="5min",
            on_unit_active_sec="6h",
        ),
        JobSpec(
            name="scitex-dev-local-state-audit",
            kind="timer",
            schedule="",
            command=_local_state_audit_command(),
            description=(
                "Local-state convention drift observer. Runs `scitex-dev "
                "ecosystem audit-local-state` on a Persistent timer "
                "(OnBootSec catch-up + every 6h) and appends per-package "
                "findings + a `LOCAL-STATE-DRIFT: <N> ...` summary to "
                "~/.scitex/dev/runtime/logs/timer-local-state-audit.log. Flags "
                "rolled-own path resolvers (PS-182) and cross-package "
                "state reads (PS-145) — the config-vs-data footgun that "
                "silently shadowed the canonical ~/.scitex/todo task store "
                "(2026-07). Read-only observe pass; `|| true` so finding "
                "drift is data, not a unit failure. The check_state_drift.sh "
                "PostToolUse hook reads this log. See "
                "_ecosystem_jobs._provider._local_state_audit_command and "
                "_skills/general/01_ecosystem/12_local-state-resolution.md."
            ),
            on_boot_sec="5min",
            on_unit_active_sec="6h",
        ),
        JobSpec(
            name="scitex-dev-venv-refresh",
            kind="timer",
            schedule="",
            command=_venv_refresh_command(),
            description=(
                "Keep the shared dev venv current: editable-installs every "
                "ecosystem package with its [all] extra into the interpreter "
                "this unit runs under, using uv when present (operator "
                "ruling 2026-08-17). Pairs with ecosystem-self-pull — that "
                "job pulls the checkouts, this one makes the pulled code the "
                "code that RUNS, which is the gap that let a host serve "
                "scitex-dev 0.48.0 for weeks while its own checkout was on "
                "0.51.0 (measured 2026-08-17; two agents spent an hour on a "
                "root cause that was one frozen copy). `-U` is ON here "
                "because currency is the product; it is OFF for interactive "
                "`ecosystem install` so a manual run cannot silently move a "
                "dependency. Daily rather than hourly: [all] pulls torch / "
                "jax / tensorflow, so a fast cadence is bandwidth and disk, "
                "not freshness. NOT a substitute for per-package venvs — a "
                "shared env has every peer installed, so a MISSING dependency "
                "declaration is invisible in it by construction. `|| true` "
                "so one leaf's unresolvable extra is a log finding, not a "
                "failed unit. See _ecosystem._git_ops.install_all."
            ),
            on_boot_sec="10min",
            on_unit_active_sec="1d",
        ),
        JobSpec(
            name="scitex-dev-host-config-check",
            kind="timer",
            schedule="",
            command=_host_config_check_command(),
            description=(
                "Declared HOST-state observer. Runs `scitex-dev ecosystem "
                "host-config check` on a Persistent timer (OnBootSec "
                "catch-up + every 6h) and appends a per-spec verdict "
                "(ok / absent / drift) to "
                "~/.scitex/dev/runtime/logs/timer-host-config-check.log and "
                "to the federation's own audit trail at "
                "~/.scitex/dev/runtime/logs/host-config.log. Aggregates "
                "every leaf's `scitex_dev.host_config` provider — the same "
                "entry-point federation as `scitex_dev.jobs` and "
                "`scitex_dev.system_deps`, applied to host-level state "
                "(journald persistence, sysctl drop-ins) that used to be "
                "configured by hand with sudo and therefore left no record "
                "of what was set or why (operator ruling 2026-08-12). "
                "UNPRIVILEGED and READ-ONLY: `check` never writes, so the "
                "timer reports drift rather than converging it — "
                "`host-config apply` is the deliberate root act. The "
                "OnBootSec catch-up is the load-bearing one: a reboot is "
                "exactly when host config is most likely to have been lost. "
                "`|| true` so finding drift is data, not a unit failure. "
                "See _ecosystem_jobs._provider._host_config_check_command "
                "and scitex_dev.host_config."
            ),
            on_boot_sec="5min",
            on_unit_active_sec="6h",
        ),
        JobSpec(
            name="scitex-dev-pr-expire",
            kind="cron",
            schedule="30 3 * * *",
            command=_pr_expire_command(),
            description=(
                "Fleet 3-day PR-expiry primitive. Runs `scitex-dev "
                "ecosystem pr expire --all --days 3` daily (03:30). "
                "SHIPS IN --dry-run (REPORT) MODE: it lists expiring PRs "
                "fleet-wide to ~/.scitex/dev/runtime/logs/cron-pr-expire.log and "
                "mutates NOTHING. Flip --dry-run to --apply ONLY after a "
                "human-validated fleet-wide dry-run — constitution §2, do "
                "NOT auto-mass-close 12 repos on first fire. --apply is "
                "fail-closed: one intent-registry card (branch + head SHA "
                "per PR) is written before any close. See "
                "_ecosystem.pr_expire.run_expire."
            ),
        ),
    ]


# EOF
