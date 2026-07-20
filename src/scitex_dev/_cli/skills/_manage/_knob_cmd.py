#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`scitex-dev skills {status,enable,disable}` — the skills-knob subcommands.

Thin wrapper over the shared knob-command builder so the `skills` and `mcp`
groups expose an identical knob surface.
"""

from ..._knob_commands import add_knob_commands


def register(skills):
    """Attach the skills knob subcommands (status/enable/disable) to *skills*."""
    add_knob_commands(skills, "skills")


# EOF
