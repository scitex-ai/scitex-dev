#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_evaluate.py
"""Comparing one declaration against a host. Never writes, never needs root."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_logger = logging.getLogger(__name__)

from ._spec import (
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    STATE_PRECONDITION_UNMET,
    STATE_UNREADABLE,
    HostConfigSpec,
    resolve_command,
)

@dataclass(frozen=True)
class HostConfigStatus:
    """The result of comparing one ``HostConfigSpec`` against a host."""

    spec: HostConfigSpec
    state: str
    detail: str

    @property
    def needs_apply(self) -> bool:
        """Whether ``--apply`` would (be allowed to) change anything."""
        return self.state in (STATE_ABSENT, STATE_DRIFT)


def evaluate(
    spec: HostConfigSpec,
    *,
    root: str = "/",
    hostname: str | None = None,
) -> HostConfigStatus:
    """Compare ``spec`` against the live host WITHOUT changing anything.

    Pure observation -- never writes, never needs root, so the periodic
    job can run unprivileged and still be honest about what it sees.

    Five outcomes, and the split between ``absent`` and ``drift`` is
    the whole point of this module:

    * ``not_applicable`` -- ``spec.hosts`` excludes this host.
    * ``precondition_unmet`` -- ``spec.requires_command`` is not on
      PATH, so writing the file would produce something no daemon
      reads. Reported, never written: a correct-looking file that
      nothing consumes is worse than a missing one, because it reports
      ``ok`` forever afterwards.
    * ``ok`` -- file present, content byte-identical, mode as declared.
      A second run of a converged host reports this for everything;
      that IS the "second run is a no-op and says so" contract.
    * ``absent`` -- no file. Converging this is safe: nothing is being
      overwritten, so ``--apply`` creates it.
    * ``drift`` -- the file exists but differs. SOMEONE OR SOMETHING
      CHANGED IT. This is never silently corrected: it is reported, and
      overwriting it takes an explicit ``--force`` (which backs the old
      file up first). Quietly re-converging drift would destroy both
      the evidence and the reason it happened.

    ``root`` prefixes ``spec.path`` so tests can evaluate against a
    tmp_path instead of the real ``/etc``.
    """
    hostname = hostname if hostname is not None else socket.gethostname()
    if not spec.applies_to(hostname):
        return HostConfigStatus(
            spec,
            STATE_NOT_APPLICABLE,
            f"declared for {', '.join(spec.hosts)}; this host is {hostname}",
        )

    if spec.requires_command and shutil.which(spec.requires_command) is None:
        return HostConfigStatus(
            spec,
            STATE_PRECONDITION_UNMET,
            f"{spec.requires_command!r} is not installed, so {spec.path} "
            f"would be read by nothing",
        )

    target = Path(root) / spec.path.lstrip("/")
    if not target.exists():
        return HostConfigStatus(spec, STATE_ABSENT, f"{spec.path} does not exist")

    try:
        actual = target.read_text(encoding="utf-8")
    except OSError as exc:
        # Unreadable is NOT "ok" and NOT "absent" -- we genuinely do not
        # know, and a success-shaped answer here would be the classic
        # "the check never ran" failure. Report it as drift so it stays
        # visible and never gets auto-overwritten.
        return HostConfigStatus(spec, STATE_DRIFT, f"{spec.path} unreadable: {exc}")

    actual_mode = oct(target.stat().st_mode & 0o777)[2:].zfill(4)
    want_mode = spec.mode.zfill(4)
    if actual != spec.content:
        return HostConfigStatus(
            spec,
            STATE_DRIFT,
            f"{spec.path} content differs from the declaration",
        )
    if actual_mode != want_mode:
        return HostConfigStatus(
            spec,
            STATE_DRIFT,
            f"{spec.path} mode is {actual_mode}, declared {want_mode}",
        )
    return HostConfigStatus(spec, STATE_OK, f"{spec.path} matches the declaration")




def directives_of(content: str) -> dict[str, str]:
    """Parse the EFFECTIVE ``key=value`` settings out of a config body.

    Comments are not settings. Without this, a test asserting "we do not
    leave ``Storage=auto``" matches the *explanation* of why auto is
    wrong, sitting in a comment two lines above ``Storage=persistent``
    -- a false failure that trains people to weaken the assertion. The
    parser keeps such tests honest by looking only at live directives.
    """
    out: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";", "[")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out

# EOF
