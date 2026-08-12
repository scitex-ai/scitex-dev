#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/__init__.py
"""Federated HOST-LEVEL configuration declaration for the SciTeX ecosystem.

Every scitex leaf declares the *host* state it needs -- a journald
drop-in, an audit ruleset, a requested DHCP address -- by registering a
callable under the ``scitex_dev.host_config`` entry-point group;
``discover_host_config()`` aggregates them. This is the same entry-point
federation used by ``scitex_dev.jobs`` / ``discover_jobs`` and
``scitex_dev.system_deps`` / ``discover_system_deps``, applied to the one
remaining layer that was still being configured by hand.

WHY A DECLARATION AND NOT AN ad-hoc ``sudo`` SESSION
----------------------------------------------------
Operator ruling, 2026-08-12: privileged host changes typed into a shell
leave no record, so months later nobody can tell *intent* from *drift* --
which of the current settings were deliberate, and which are the residue
of a forgotten debugging session. A declaration is a file someone can
read, diff and review; the applier is idempotent; and what it changed is
reported rather than silently converged.

THE OUTCOMES, AND WHY THERE ARE SIX
-----------------------------------
Each one exists because collapsing it into a neighbour would let a
host report success while the goal was unmet:

* ``ok`` -- file matches the declaration.
* ``absent`` -- nothing there; safe to converge.
* ``drift`` -- present and DIFFERENT. Reported, never silently
  corrected: overwriting destroys the evidence and the reason.
* ``not_applicable`` -- ``hosts`` excludes this machine.
* ``precondition_unmet`` -- the daemon that would READ this file is not
  installed, so writing it would produce a file nothing consumes and
  every later check would answer ``ok`` forever.
* ``unreadable`` -- the file could not be read, so NO COMPARISON WAS
  MADE. Distinct from ``drift`` (which claims a comparison happened and
  found a difference) and from ``absent`` (which claims the file is not
  there). ``/etc/audit/rules.d/`` is root-only, so an unprivileged
  check genuinely cannot see it, and must say so.

Example provider (in a leaf package)::

    # scitex_agent_container/_host_config.py
    from scitex_dev.host_config import HostConfigSpec

    def provide() -> list[HostConfigSpec]:
        return [
            HostConfigSpec(
                name="sac.tmpfiles-state",
                path="/etc/tmpfiles.d/scitex-agent-state.conf",
                content="d /state 0755 ywatanabe ywatanabe -\\n",
                purpose="agent state dir survives reboot",
                provider="scitex-agent-container",
                apply_command="systemd-tmpfiles --create",
            ),
        ]

    # pyproject.toml
    # [project.entry-points."scitex_dev.host_config"]
    # scitex-agent-container = "scitex_agent_container._host_config:provide"

``scitex-dev ecosystem host-config`` then surfaces, checks and (with
root) applies the declaration automatically.

This module is a thin orchestrator; the implementation lives in
``_spec`` (the declaration), ``_discover`` (the federation),
``_evaluate`` (comparison), ``_apply`` (convergence + audit trail) and
``_declarations`` (scitex-dev's own).
"""

from __future__ import annotations

from ._discover import discover_host_config
from ._evaluate import HostConfigStatus, directives_of, evaluate
from ._spec import (
    ENTRY_POINT_GROUP,
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    STATE_PRECONDITION_UNMET,
    STATE_UNREADABLE,
    HostConfigSpec,
    resolve_command,
)

__all__ = [
    "HostConfigSpec",
    "HostConfigStatus",
    "ENTRY_POINT_GROUP",
    "STATE_OK",
    "STATE_ABSENT",
    "STATE_DRIFT",
    "STATE_NOT_APPLICABLE",
    "STATE_PRECONDITION_UNMET",
    "STATE_UNREADABLE",
    "discover_host_config",
    "evaluate",
    "directives_of",
    "resolve_command",
]

# EOF
