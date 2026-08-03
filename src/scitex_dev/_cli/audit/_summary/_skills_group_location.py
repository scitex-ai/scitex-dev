#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Where the §1a `skills` group is allowed to live.

Its own module rather than a helper inside ``_audit.py`` because it
answers a question both §1a and §13 ask, and the answer has to be the
same one in both places. Keeping it here also gives the rule a test file
to mirror.
"""

from __future__ import annotations

import click


def resolve_skills_group(cmd: click.Group) -> tuple[click.Group | None, str]:
    """Find the §1a `skills` group at either sanctioned location.

    §13 lists `skills` among the six self-maintenance verbs that MUST
    nest under `dev`, so a §1a that only looks at top level makes the two
    rules unsatisfiable at once: satisfy §13 and §1a reports the group
    missing; satisfy §1a and §13 reports it un-nested. Measured on
    scitex-dev itself 2026-08-03, mid-migration — the package that owns
    both rules was the first to be caught between them, and every package
    that adopts §13 hits it next.

    `dev` is checked FIRST because it is where the rule now says the
    group belongs; top level remains accepted for packages that have not
    migrated yet. A Phase W alias does not count: it is a leaf
    `click.Command`, so the isinstance check rejects it, and it should —
    an alias forwards, it does not host the verbs.

    Returns the group (or None) and the path to name it by in findings,
    so a message about a missing verb points at the real location.
    """
    dev = cmd.commands.get("dev")
    if isinstance(dev, click.Group):
        nested = dev.commands.get("skills")
        if isinstance(nested, click.Group):
            return nested, "dev skills"

    top = cmd.commands.get("skills")
    if isinstance(top, click.Group):
        return top, "skills"

    return None, "skills"


__all__ = ["resolve_skills_group"]


# EOF
