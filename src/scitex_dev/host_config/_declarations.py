#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_declarations.py
"""scitex-dev's own HOST-LEVEL configuration declarations.

Registered under the same ``scitex_dev.host_config`` entry-point
federation every leaf uses, so the aggregator
(``discover_host_config``) picks it up like any downstream provider --
the keystone eats its own dog food, exactly as ``_system_deps.py`` does
for apt packages.

The first declaration is PERSISTENT JOURNALD, and it exists because of a
specific incident: on 2026-08-11 at 16:07:58 JST the shared tmux server
on a fleet host vanished and took eleven agents with it. The cause was
never determined. A deliberate ``tmux kill-server`` leaves no trace of
itself, so the surrounding system journal is the only evidence that
could ever have settled it -- and journald's default ``Storage=auto``
silently degrades to VOLATILE (RAM-only, gone at reboot) on any host
where ``/var/log/journal`` happens not to exist. "Happens not to exist"
is not a property you want your only forensic record to depend on.
"""

from __future__ import annotations

from scitex_dev.host_config import HostConfigSpec

#: Body of the journald drop-in. A drop-in under ``journald.conf.d/``
#: rather than an edit to ``/etc/systemd/journald.conf``: additive,
#: removable, survives a systemd package upgrade, and leaves the
#: distro's own file pristine so the diff of what WE changed is the
#: whole file rather than a hunk buried in a hundred commented lines.
JOURNALD_PERSISTENT = """\
# Managed by scitex-dev. Do not edit by hand -- edits show up as DRIFT in
# `scitex-dev ecosystem host-config check` and are deliberately NOT
# auto-reverted, so a hand edit will sit there being reported until
# someone decides which side is right.
#
# Declared by HostConfigSpec "journald.persistent" in
# scitex_dev/host_config/_declarations.py. To change this file, change that
# declaration and let the job apply it.
#
# WHY: 2026-08-11 16:07:58 JST, a shared tmux server died and took 11
# agents with it; the cause was undeterminable because a `tmux
# kill-server` leaves no trace and the journal was not guaranteed to
# outlive a reboot. `Storage=auto` -- the default -- keeps the journal in
# RAM whenever /var/log/journal is missing, and loses it at reboot.
# `Storage=persistent` CREATES that directory and guarantees the journal
# survives, so the next incident is still investigable tomorrow.
[Journal]
Storage=persistent
SystemMaxUse=4G
"""


def provide() -> list[HostConfigSpec]:
    """Host-level configuration scitex-dev itself requires."""
    return [
        HostConfigSpec(
            name="journald.persistent",
            path="/etc/systemd/journald.conf.d/99-scitex-persistent.conf",
            content=JOURNALD_PERSISTENT,
            purpose=(
                "Keep the system journal across reboots so a fleet incident "
                "is still investigable afterwards (2026-08-11 tmux-server "
                "death, 11 agents, cause undeterminable for want of logs)."
            ),
            provider="scitex-dev",
            mode="0644",
            # Restarting journald re-reads the drop-in and, for
            # Storage=persistent, creates /var/log/journal. It is a safe
            # restart: journald is socket-activated and clients block
            # briefly rather than losing messages. This runs ONLY on a
            # pass that actually changed the file.
            apply_command="systemctl restart systemd-journald",
            # OBSERVATION, not config. Reading the file back would be a
            # tautology; `--list-boots` reports the boots the journal
            # still holds records for, so more than one entry is direct
            # evidence that the journal survived a reboot boundary.
            verify_command="journalctl --list-boots",
            requires_root=True,
        ),
    ]


__all__ = ["JOURNALD_PERSISTENT", "provide"]

# EOF
