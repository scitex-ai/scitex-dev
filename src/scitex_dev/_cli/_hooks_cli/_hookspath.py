#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``core.hooksPath`` wiring, shared by every real-git-hook leaf.

A script at ``<repo>/.githooks/<name>`` is INERT until git is told to
look there — by default git only reads ``.git/hooks/``. So installing
the symlink is half an installation, and the half that is missing has no
symptom: the hook is present, readable, executable, and never runs.

This module exists because there are now TWO leaves that need the second
half (``enable-pre-push`` and ``enable-pre-commit``), and the wiring has
one rule that must not drift between them:

    ADDITIVE, THEN REFUSE.
    unset            -> set to .githooks
    already .githooks -> no-op
    anything else    -> REFUSE unless forced

An operator who pointed ``core.hooksPath`` somewhere of their own has
made a decision, and silently clobbering it is how a helpful installer
disables somebody's tooling. The prior value is always printed when
``--force`` takes effect.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: The directory every scitex-dev git hook deploys into.
HOOKS_DIR = ".githooks"

#: ``core.hooksPath`` is already ours; nothing to do.
WIRED = "wired"

#: It was unset and is now ours.
CONFIGURED = "configured"

#: It pointed elsewhere and ``force`` was given.
FORCED = "forced"

#: It points elsewhere and ``force`` was not given.
REFUSED = "refused"

#: ``git`` itself could not be run.
NO_GIT = "no-git"

#: ``git config`` ran and failed.
FAILED = "failed"


def read_hookspath(project: Path | str) -> str | None:
    """Current ``core.hooksPath`` for ``project``.

    ``""`` means git answered and the key is unset; ``None`` means git
    could not be run at all. Collapsing those two would report "unset"
    for a machine with no git and then try to configure it.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(project), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    return proc.stdout.strip()


def plan_hookspath(current: str | None, *, force: bool) -> str:
    """What :func:`wire_hookspath` WOULD do, given ``current``. Pure.

    Split out so ``--dry-run`` and the real run cannot disagree: the
    dry-run reports this function's answer, and the real run acts on it.
    """
    if current is None:
        return NO_GIT
    if current == HOOKS_DIR:
        return WIRED
    if not current:
        return CONFIGURED
    return FORCED if force else REFUSED


def wire_hookspath(
    project: Path | str, *, force: bool = False
) -> tuple[str, str, str]:
    """``(status, previous value, detail)``. Writes only when it must.

    ``status`` is one of :data:`WIRED`, :data:`CONFIGURED`,
    :data:`FORCED`, :data:`REFUSED`, :data:`NO_GIT`, :data:`FAILED`.
    """
    current = read_hookspath(project)
    planned = plan_hookspath(current, force=force)
    if planned in (NO_GIT, WIRED, REFUSED):
        return planned, current or "", ""
    proc = subprocess.run(
        ["git", "-C", str(project), "config", "core.hooksPath", HOOKS_DIR],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return FAILED, current or "", (proc.stderr or proc.stdout).strip()
    return planned, current or "", ""


__all__ = [
    "CONFIGURED",
    "FAILED",
    "FORCED",
    "HOOKS_DIR",
    "NO_GIT",
    "REFUSED",
    "WIRED",
    "plan_hookspath",
    "read_hookspath",
    "wire_hookspath",
]

# EOF
