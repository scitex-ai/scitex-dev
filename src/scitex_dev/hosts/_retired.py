#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RETIRED ssh aliases — a deny-list of names that no longer reach anything.

Why this may be PACKAGED when routes may not
--------------------------------------------
:mod:`scitex_dev.hosts._seed` ships default host records, and that was a
mistake for ROUTE data: "``nas`` reaches this machine" is a claim about the
world, the world changes, and a wheel cannot. Measured 2026-08-11 — the
seeded registry in this container was a month old, served three ssh aliases
retired four days earlier, and was missing four compute hosts entirely.

A RETIREMENT is the opposite kind of fact. Once a name stops resolving it
does not start again; the set only grows. So a packaged deny-list can be
stale only by being INCOMPLETE, never by being WRONG — the same distinction
that makes the packaged runner-destination FLOOR sound for PS-224 while the
packaged route table is not. An incomplete deny-list misses a warning; an
incorrect route table hands out a connection that cannot be made.

Why a deny-list reaches what a corrected default cannot
-------------------------------------------------------
``create_default_hosts_yaml`` no-ops once the file exists, so a container
that seeded a bad registry keeps it forever: the only code that would fix
it is the code that never runs again. Correcting the seed (#551) helps new
installs and NOTHING already deployed. This check runs on every
:func:`~scitex_dev.hosts.resolve` call, so it reaches files the seeder will
never touch.

Reported by dotfiles 2026-08-11, who found it by live-firing a fix instead
of trusting it. The consequence — that a corrected default cannot repair a
frozen file — is the half neither of us had until they measured it.

Rollout
-------
WARN phase. This module only reports; nothing raises. ``list_hosts`` /
``resolve`` are a published contract and a registry that suddenly throws
would break every caller in every already-seeded container at once, which
is exactly the population this is meant to help. Promotion to an error
follows the same W -> E ladder ``_ecosystem.click_compat`` uses for CLI
deprecations, once the fleet's registries have been refreshed.
"""

from __future__ import annotations

import logging

__all__ = ["RETIRED_SSH_ALIASES", "successor_for", "retirement_warning"]

logger = logging.getLogger(__name__)

#: ``retired alias -> successor``, read from the retirement mechanism itself.
#:
#: The stub installed for each dead name logs ``old=X new=Y`` on every hit to
#: ``~/.ssh/retired-alias-hits.log``; these pairs are transcribed from that
#: log rather than inferred from the naming pattern. That distinction is not
#: pedantic — the highest-traffic entry is ``nas -> scitex-nas-03``, and a
#: pattern would confidently produce ``scitex-nas-01``.
#:
#: Retired 2026-08-07. Hit counts at 2026-08-11, for scale:
#:   nas 1074 (scitex-orochi's 5-minute liveness probe), nas2 83, nas-03 33,
#:   nas-01 6, nas-02 5, nas1 4, nas3 1, ug 1.
RETIRED_SSH_ALIASES: dict[str, str] = {
    "nas": "scitex-nas-03",
    "nas1": "scitex-nas-01",
    "nas2": "scitex-nas-02",
    "nas3": "scitex-nas-03",
    "nas-01": "scitex-nas-01",
    "nas-02": "scitex-nas-02",
    "nas-03": "scitex-nas-03",
    "ug": "scitex-nas-03",
}

def successor_for(ssh_alias: str | None) -> str | None:
    """Return the live successor of a RETIRED alias, or None.

    None means "not a known-retired name" — which is NOT the same as "this
    alias works". The deny-list can only ever be incomplete, so a None here
    is the absence of a recorded retirement, never a reachability check.
    """
    if not ssh_alias:
        return None
    return RETIRED_SSH_ALIASES.get(ssh_alias.strip())


def retirement_warning(host_name: str, ssh_alias: str) -> str:
    """The message emitted for a registry row pointing at a dead alias."""
    successor = RETIRED_SSH_ALIASES[ssh_alias.strip()]
    return (
        f"host registry: {host_name!r} routes through ssh alias "
        f"{ssh_alias!r}, which was RETIRED on 2026-08-07 and resolves to "
        f"nothing — the stub prints its successor and exits 255. Use "
        f"{successor!r}. This registry is stale: the seeder writes defaults "
        f"only when the file is ABSENT, so a corrected package default "
        f"cannot repair it. Fix the `ssh_alias` in your hosts.yaml, or "
        f"delete the file and let it re-seed."
    )


def warn_if_retired(host_name: str, ssh_alias: str | None) -> str | None:
    """Log a warning if ``ssh_alias`` is retired; return the message or None.

    Returns the message as well as logging it, so callers can act on the
    decision without capturing log output and a CLI can put it on stderr.
    The logging lives here rather than at each call site so every entry
    point reports identically.

    NO PROCESS-LEVEL DEDUP, deliberately. The first version kept a module
    set of already-warned ``(host, alias)`` pairs so a repeated
    ``list_hosts()`` would not reprint. That made the function's behaviour
    depend on what had run before it in the same interpreter — three tests
    failed on ordering alone, and any consumer calling two different code
    paths would have inherited the same surprise. Hidden global state that
    changes an answer based on history is the defect family this whole
    module exists to catch, so it does not belong in the catcher.

    Suppressing repeats is a CONSUMER's decision and the logging system
    already implements it (a filter, or a handler that collapses
    duplicates). A registry that is still broken on the tenth call has not
    become less broken.
    """
    if successor_for(ssh_alias) is None:
        return None
    assert ssh_alias is not None  # narrowed by successor_for
    message = retirement_warning(host_name, ssh_alias)
    logger.warning(message)
    return message


# EOF
