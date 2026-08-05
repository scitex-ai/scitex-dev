#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integration-command registration for the scitex-dev CLI.

Extracted from ``_root.py`` to keep that orchestrator under the per-file
line budget. Registers the cross-cutting integration groups, split by the
§13 discriminator (doctrine ``20_dev-commands.md``):

DOMAIN — what the tool IS, mounted at top level:

* ``mcp``     — MCP server lifecycle.
* ``creds``   — credential distribution.
* ``service`` — keep a declared ``kind='service'`` daemon alive
                (systemd --user or respawn fallback).
* ``host``    — the SciTeX-wide host registry (where is host X, and
                what's its ~/.scitex root?).

SELF-MAINTENANCE — how the tool manages ITSELF on this host, mounted
under ``dev``:

* ``cron``    — ecosystem-wide managed cron.
* ``hooks``   — git/agent hook management.

The test, from the doctrine: "is this command about the tool's DOMAIN,
or about maintaining/developing the tool itself?" `<pkg> --help` then
reads as the tool, not the tool's own upkeep.
"""

from __future__ import annotations

import click


def register_integration_commands(main: click.Group, dev: click.Group) -> None:
    """Register the integration groups, domain on ``main``, upkeep on ``dev``.

    Two groups rather than one because the §13 split is the whole point:
    passing a single group would put ``cron`` and ``hooks`` back at top
    level, which is the state this migration exists to leave.
    """
    from ._mcp_cmds import register_mcp_commands
    from .creds import register_creds_commands
    from .cron import register_cron_commands
    from ._hooks_cli import register_hooks_commands
    from .service import register_service_commands
    from ._hosts import register_host_commands

    register_mcp_commands(main)
    register_creds_commands(main)
    register_service_commands(main)
    register_host_commands(main)

    register_cron_commands(dev)
    register_hooks_commands(dev)


__all__ = ["register_integration_commands"]


# EOF
