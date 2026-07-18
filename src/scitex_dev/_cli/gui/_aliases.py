#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase W back-compat aliases for the pre-`gui` dashboard command paths.

§12 recognises exactly this migration: a legacy gui-adjacent leaf stops
being a violation once it is a hidden alias carrying `_deprecated_alias`
metadata and forwarding to the canonical group. So nobody's muscle
memory or script breaks — `ecosystem dashboard list -vv` still runs,
prints one deprecation line on stderr, and lands on `gui list -vv`.

Two rungs are wired here:

* ``ecosystem dashboard [SUB ...]`` → the whole ``gui`` GROUP, so every
  old subcommand keeps resolving (``list``/``export`` by their own
  names, ``start``/``start-tui`` via the in-group aliases below).
* ``ecosystem start-dashboard [OPTS]`` → ``gui open``, which accepts the
  legacy ``--no-browser`` / ``--background`` / ``--debug`` flags so the
  forward never dies on an unknown option.

The one behavioural change: `start-dashboard` without `--background`
used to block in the foreground with a browser; `gui open` always
serves detached. Foreground is now `gui serve` (headless, per doctrine).
"""

from __future__ import annotations

import click

from ..._ecosystem.click_compat import deprecated_alias

# The release these aliases disappear in (Phase R). Bumped as a pair
# with the doctrine's deprecation ladder, not per-command.
REMOVE_IN = "0.34"

__all__ = ["REMOVE_IN", "register_in_group", "register_on_ecosystem"]


def register_in_group(gui: click.Group) -> None:
    """Alias the two renamed verbs INSIDE the `gui` group.

    `ecosystem dashboard start` forwards the raw token `start` into the
    `gui` group, so `gui start` has to resolve for that path to keep
    working — hence the alias lives here rather than only on `ecosystem`.
    """
    deprecated_alias(
        gui,
        "start",
        target="watch",
        target_name="gui watch",
        remove_in=REMOVE_IN,
        phase="warn",
    )


def register_on_ecosystem(ecosystem: click.Group, gui: click.Group) -> None:
    """Alias the two legacy `ecosystem` entry points onto the `gui` group."""
    deprecated_alias(
        ecosystem,
        "dashboard",
        target=gui,
        target_name="gui",
        remove_in=REMOVE_IN,
        phase="warn",
    )
    deprecated_alias(
        ecosystem,
        "start-dashboard",
        target=gui.commands["open"],
        target_name="gui open",
        remove_in=REMOVE_IN,
        phase="warn",
    )


# EOF
