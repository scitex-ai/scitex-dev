#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_evaluate.py
"""Compare a declaration against the live host, WITHOUT changing anything.

Split out of ``host_config/__init__.py`` on 2026-08-15. That module answered
two different questions — "what is declared" (discovery) and "what is true on
this host" (evaluation) — which are different failure modes with different
tests. `_apply.py` already owned the "change the host" half; evaluation sitting
in `__init__` was the odd one out.

The public surface is unchanged: `__init__` re-exports everything here.
"""

from __future__ import annotations

import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

from ._states import (
    STATE_ABSENT,
    STATE_DRIFT,
    STATE_NOT_APPLICABLE,
    STATE_OK,
    STATE_PRECONDITION_UNMET,
)
from ._volatility import volatile_reason


@dataclass(frozen=True)
class HostConfigStatus:
    """The result of comparing one ``HostConfigSpec`` against a host."""

    spec: object
    state: str
    detail: str

    @property
    def needs_apply(self) -> bool:
        """Whether ``--apply`` would (be allowed to) change anything."""
        return self.state in (STATE_ABSENT, STATE_DRIFT)


def evaluate(
    spec,
    *,
    root: str = "/",
    hostname: str | None = None,
) -> HostConfigStatus:
    """Compare ``spec`` against the live host WITHOUT changing anything.

    Pure observation -- never writes, never needs root, so the periodic
    job can run unprivileged and still be honest about what it sees.

    Outcomes, and the split between ``absent`` and ``drift`` is the whole
    point of this module:

    * ``not_applicable`` -- ``spec.hosts`` excludes this host.
    * ``precondition_unmet`` -- the file could not do its job: either
      ``spec.requires_command`` is off PATH (no daemon would read it),
      or its filesystem is RAM-backed so a reboot erases it (see
      ``._volatility``). Reported, never written.
    * ``ok`` -- file present, content byte-identical, mode as declared.
    * ``absent`` -- no file. Converging this is safe: nothing is being
      overwritten, so ``--apply`` creates it.
    * ``drift`` -- the file exists but differs, OR we could not read it.
      SOMETHING CHANGED IT, or we do not know. Never silently corrected:
      overwriting takes an explicit ``--force`` (which backs the old file
      up first).

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

    # Real host only: under a synthetic ``root`` the evaluation is
    # hypothetical, and pytest's tmp_path is often tmpfs itself.
    if root == "/":
        volatile = volatile_reason(spec.path)
        if volatile:
            return HostConfigStatus(spec, STATE_PRECONDITION_UNMET, volatile)

    target = Path(root) / spec.path.lstrip("/")
    try:
        present = target.exists()
    except OSError as exc:
        # UNSTATTABLE IS NOT ABSENT, and this line cost five wrong
        # diagnoses to find.
        #
        # `Path.exists()` is widely believed to swallow errors and return
        # False. It does not, and this is NOT a version quirk:
        # `_ignore_error` suppresses ENOENT/ENOTDIR/EBADF/ELOOP and has
        # NEVER covered EACCES, so an untraversable parent has always
        # raised here. Measured on the real path across 3.11.15, 3.12.13
        # and 3.13.15 -- all three raise (scitex-hpc, 2026-08-15, correcting
        # an earlier "on 3.12" note of mine that would have scoped any
        # follow-up to the wrong interpreters).
        #
        # Reporting ABSENT here would be actively dangerous, because absent
        # is the state `apply` CREATES -- an unreadable root-owned file
        # would be called missing and then written.
        #
        # MEASURED 2026-08-15: /etc/audit is `drwxr-x--- root:root` on
        # scitex-compute-04 and ABSENT on 01/02/03, so a spec declaring a
        # file under /etc/audit/rules.d/ raised PermissionError(13) HERE and
        # aborted the whole `host-config apply` CLI before it printed
        # anything -- on that host and no other. The discriminator is the
        # spec's `requires_command` precondition: without auditd on PATH the
        # spec short-circuits above and never reaches this line, so it is
        # inert everywhere auditd is absent and lethal exactly where it is
        # installed. That is why it read as a flaky per-leg CI failure for
        # hours: the leg that landed on 04 failed, at any Python version.
        #
        # DRIFT, for the same reason the unreadable branch below gives:
        # it stays visible and is never auto-overwritten.
        return HostConfigStatus(
            spec, STATE_DRIFT, f"{spec.path} could not be stat'd: {exc}"
        )
    if not present:
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


__all__ = ["HostConfigStatus", "directives_of", "evaluate"]

# EOF
