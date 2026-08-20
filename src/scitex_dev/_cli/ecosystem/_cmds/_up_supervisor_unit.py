#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Supervisor systemd unit — the ONE artefact ``ecosystem up`` registers.

Extracted from ``_up.py`` to stay under the per-file line limit and to
keep the unit-text generator unit-testable without booting the rest of
the orchestrator. See module docstring on ``_up.py`` for the operator
policy this implements (post-2026-06-14 redesign: ONE collective
``scitex-dev-ecosystem.service`` instead of per-leaf units).

Public surface
--------------
* :data:`SUPERVISOR_UNIT_NAME` — the canonical filename.
* :func:`build_supervisor_unit_text` — generate the unit body with the
  absolute ``ExecStart=`` path resolved at call time (so test seams +
  PATH probes both work).
* :func:`write_supervisor_unit` — write the unit text to a directory.
  Idempotent; mkdir-parents.
"""

from __future__ import annotations

import shlex
from pathlib import Path

# The PATH systemd --user gives a unit that declares none. Kept explicit
# rather than read from os.environ at build time: the unit text must be
# reproducible on any host, and inheriting the *installing* shell's PATH
# would bake one operator's ambient environment into a managed file.
_SYSTEM_PATH_ENTRIES = (
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/usr/bin",
    "/sbin",
    "/bin",
)

# The systemd unit filename. ``scitex-dev-ecosystem`` chosen for symmetry
# with the old (now-deprecated) ``scitex-dev-ecosystem-reconcile.service``
# the operator was familiar with; the ``.service`` suffix matches the
# Type=simple long-running shape.
SUPERVISOR_UNIT_NAME = "scitex-dev-ecosystem.service"

# The card-store identity the supervisor's CHILDREN write under.
#
# MEASURED 2026-08-20 on scitex-compute-04, reading the live supervisor's
# /proc/<pid>/environ: SCITEX_CARDS_AGENT_ID and the retired
# SCITEX_TODO_AGENT_ID were BOTH unset (control: HOME present, 18 vars
# read, so the read itself worked). `ci-watch` had filed ZERO cards
# against 351 red-CI detections, 347 of them failing with `creator
# unresolved` — scitex-cards refuses to guess a creator rather than
# silently attributing to blank/'unknown'. Nothing alarmed, because a
# periodic job's exit code reaches only its own ledger.
#
# This is the Environment=PATH defect below, one variable over: on
# 2026-08-19 a bare PATH broke every shell-bodied child 497/497, equally
# silently. Children inherit THIS unit's environment, so whatever they
# need must be declared here — systemd --user inherits no login shell.
#
# The value names the SOFTWARE that writes, matching the convention
# already used for automated actors (notifyd). Deliberately not a
# per-host agent name: this unit is installed on every host while the
# scitex-dev AGENT runs on one, so a host-derived identity would claim
# an agent that is not present. Card `assignee` still carries who must
# ACT; this is only `created_by`.
#
# DELIBERATELY NOT DECLARED HERE: SCITEX_CARDS_DB.
#
# It is absent from this unit's environment too, and a draft of this change
# added it — on the theory that a missing DSN made the store resolver fall
# back silently to SQLite. scitex-cards MEASURED that theory and withdrew
# it: with SCITEX_CARDS_DB unset, the config tier still returns
# `postgresql://…:55432/scitex_cards`, and the zero-config SQLite default
# was abolished 2026-08-13 (it now raises StoreTargetNotConfigured).
# Verified on the DEPLOYED installs, not just a checkout.
#
# So the absence is real and the consequence is not. Declaring it would be
# worse than inert: an env var OVERRIDES the config tier, which would pin
# one literal DSN into every host's generated unit and take the value away
# from the layer that is supposed to own it per host.
#
# The identity variable below has no such alternative path — nothing
# supplies a creator when the environment does not — which is why one is
# declared and the other is not. Absent-in-the-environment was true of
# both; only one of them explained a measured failure.
_CHILD_ENV = ("SCITEX_CARDS_AGENT_ID=scitex-dev",)


def build_supervisor_unit_text() -> str:
    """Return the supervisor unit text with ``ExecStart=`` absolutised.

    Built dynamically (not a module-level constant) so the
    ``ExecStart=`` line carries the absolute path to ``scitex-dev`` as
    resolved from the operator's ambient PATH at call time. systemd
    ``--user`` runs under a deliberately minimal PATH that excludes
    most Python venvs; emitting a bare ``scitex-dev`` would 127 on
    every boot — same root-cause that fixed the legacy reconcile unit
    in PR #163 / scitex-dev v0.17.x.

    Unit shape:

    * ``Type=simple`` — the supervisor IS the foreground process. No
      fork, no PID file. Avoids the legacy oneshot's "stayed inactive
      after exit" trap.
    * ``Restart=always`` — if the supervisor itself ever crashes,
      systemd brings it back. Children are restarted by the
      supervisor; the supervisor is restarted by systemd.
    * ``ExecReload=/bin/kill -HUP $MAINPID`` — surfaces the systemd-
      idiomatic ``systemctl --user reload scitex-dev-ecosystem.service``
      for "re-read your config". The supervisor's SIGHUP handler
      re-runs ``reconcile()``.
    * ``KillSignal=SIGTERM`` + ``TimeoutStopSec=30s`` — graceful child
      shutdown: the supervisor's SIGTERM handler walks the registry,
      SIGTERMs each child, waits the grace, then SIGKILLs stragglers.
    """
    # Import lazily so ``_up_supervisor_unit`` itself stays cheap to
    # import (no jobs/_systemd at module-load time for callers that
    # only need ``SUPERVISOR_UNIT_NAME``).
    from ....jobs._systemd import resolve_execstart

    execstart = resolve_execstart("scitex-dev ecosystem run")
    # Absolutising ExecStart (above) fixes the supervisor's OWN exec and
    # nothing about its CHILDREN. A periodic job's body is a shell string
    # that calls `scitex-dev` by BARE NAME, and the children inherit this
    # unit's environment — so under the bare --user PATH, /bin/sh cannot
    # resolve the console script and the job exits 127 after ~1s.
    #
    # MEASURED 2026-08-19 on all four reachable hosts: every job with a
    # shell body was failing 100%, and the load-bearing one was
    # scitex-dev-ecosystem-self-pull at 497/497 over 16.6h — the job that
    # keeps each host's checkout tracking the repo. Its log held one line,
    # repeated: `/bin/sh: 1: scitex-dev: not found`. Nothing alarmed,
    # because a periodic job's exit code is only written to its own ledger.
    # Jobs whose argv was already absolute (sac's) were green throughout,
    # which is why this looked like "some jobs are broken" rather than one
    # environment defect.
    #
    # The venv bin is derived from the resolved ExecStart rather than from
    # sys.prefix: ExecStart is what this unit will actually run, so the two
    # cannot disagree.
    bin_dir = str(Path(shlex.split(execstart)[0]).parent)
    child_path = ":".join((bin_dir, *_SYSTEM_PATH_ENTRIES))
    return (
        "[Unit]\n"
        "Description=SciTeX ecosystem supervisor — manages every "
        "kind=service JobSpec as a child process; the SOLE per-host "
        "systemd entry for the SciTeX fleet\n"
        "Documentation=https://github.com/scitex-ai/scitex-dev\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"Environment=PATH={child_path}\n"
        + "".join(f"Environment={entry}\n" for entry in _CHILD_ENV)
        + f"ExecStart={execstart}\n"
        "ExecReload=/bin/kill -HUP $MAINPID\n"
        "Restart=always\n"
        "RestartSec=5s\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "KillSignal=SIGTERM\n"
        "TimeoutStopSec=30s\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def write_supervisor_unit(unit_dir: Path) -> Path:
    """Write the supervisor service unit. Idempotent.

    Returns the path written. Always writes the canonical text — if
    the operator hand-edited the file, a fresh ``ecosystem up`` resets
    it. Hand edits belong in the JobSpec the leaf declares, not in
    scitex-dev's managed unit.
    """
    unit_dir.mkdir(parents=True, exist_ok=True)
    path = unit_dir / SUPERVISOR_UNIT_NAME
    path.write_text(build_supervisor_unit_text(), encoding="utf-8")
    return path


__all__ = [
    "SUPERVISOR_UNIT_NAME",
    "build_supervisor_unit_text",
    "write_supervisor_unit",
]


# EOF
