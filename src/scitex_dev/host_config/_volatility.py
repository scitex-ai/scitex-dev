#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_volatility.py
"""Refuse to declare a file onto a filesystem that a reboot erases.

THE HOLE THIS CLOSES
--------------------
Measured 2026-08-12 on ``scitex-nas-01`` and ``scitex-nas-02`` (both QNAP
QTS):

    none / tmpfs rw,relatime,size=409600k,mode=755

``/`` is a 400 MB RAMDISK. ``/etc``, ``/etc/dhcp``, ``/etc/systemd``,
``/etc/audit`` and ``/var/log`` all sit on it, and QTS restores the whole
tree from firmware at every boot. So a spec applied to one of those hosts
converges, ``check`` reports ``ok``, and the setting is gone at the next
reboot -- and if a periodic job applies and then checks in the same run,
it reports ``ok`` FOREVER on a host where the configuration has never once
survived. That is a guard reporting success while its goal is unmet, which
is the failure class this whole federation exists to remove, reappearing
one layer down.

Without this check nothing stops the next person from adding an auditd
rules file, or a journald drop-in, for one of those boxes and getting a
permanently green, permanently ineffective result.

WHAT THIS DOES AND DOES NOT PROVE
----------------------------------
It proves ONE direction only. ``tmpfs`` and ``ramfs`` are RAM-backed by
definition, so a file on them is definitively lost at reboot -- that is a
fact about the filesystem type, not a guess about the distribution.

The absence of that signal proves NOTHING, and the fleet contains the
counterexample: ``scitex-nas-03`` (UGREEN, Debian 12) has a genuinely
persistent ``overlay`` root, and its ``/etc/dhcp/dhclient.conf`` is STILL
rewritten at every boot -- by ``/usr/ugreen/scripts/dhclient-start``,
which regenerates it from the interface's MAC. A filesystem check cannot
see that, and must not be read as certifying durability. It catches
volatile STORAGE; a process that rewrites a file on durable storage shows
up as ``drift`` on the next check instead, which is the honest report for
that different failure.

So this is deliberately named for what it detects -- a known-volatile
filesystem -- rather than for the reassurance it cannot give.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

_logger = logging.getLogger(__name__)

#: Filesystems that are RAM-backed by definition, so anything written to
#: them is gone at reboot. Deliberately SHORT and conservative: every
#: member here must be volatile by its own definition rather than by local
#: convention, because a false positive refuses to apply a declaration
#: that would have worked.
#:
#: ``overlay`` is NOT a member, even though it is often layered over
#: tmpfs. An overlay with a disk-backed ``upperdir`` persists perfectly
#: well (``scitex-nas-03`` and this project's own agent containers are
#: both that shape), so refusing them all would be wrong far more often
#: than it was right. An overlay whose upper really is tmpfs is a gap; it
#: is a smaller and quieter one than blocking every container.
VOLATILE_FSTYPES: frozenset[str] = frozenset({"tmpfs", "ramfs"})

#: Where the kernel publishes the mount table. Injectable so the tests can
#: use a fixture instead of whatever the machine running them happens to
#: mount -- pytest's own ``tmp_path`` is frequently tmpfs, so a test that
#: read the real table would pass or fail depending on the runner.
DEFAULT_MOUNTS_PATH = "/proc/mounts"


def _iter_mounts(mounts_path: str) -> list[tuple[str, str]]:
    """Yield ``(mount_point, fstype)`` from a ``/proc/mounts``-format file.

    Unreadable or malformed input yields an EMPTY list rather than
    raising: this feeds a check that must keep working on a host whose
    kernel does not publish a mount table (or is not Linux at all), and
    "I could not tell" has to degrade to "no volatility claim", never to
    an exception inside an unprivileged status command.
    """
    out: list[tuple[str, str]] = []
    try:
        with open(mounts_path, encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) < 3:
                    continue
                # /proc/mounts octal-escapes spaces and tabs in the mount
                # point. Decoding matters: a mount at "/mnt/my disk"
                # appears as "/mnt/my\040disk", which would otherwise
                # never match a real path.
                mount_point = (
                    fields[1]
                    .replace("\\040", " ")
                    .replace("\\011", "\t")
                    .replace("\\012", "\n")
                    .replace("\\134", "\\")
                )
                out.append((mount_point, fields[2]))
    except OSError as exc:
        _logger.debug("could not read %s: %s", mounts_path, exc)
    return out


def filesystem_of(
    path: str, *, mounts_path: str = DEFAULT_MOUNTS_PATH
) -> tuple[str, str] | None:
    """Return ``(mount_point, fstype)`` for the filesystem holding ``path``.

    Resolves by LONGEST PATH-COMPONENT prefix, which is what the kernel
    itself does. Matching on raw string prefixes would be subtly wrong in
    a way that is hard to notice: a mount at ``/etc/passwd`` (this
    project's own agent containers have exactly that, a tmpfs) is a string
    prefix of ``/etc/passwd_backup``, so a naive check would attribute a
    file on the durable root to the tmpfs beside it and refuse to write
    it.

    ``None`` when no mount matches -- an empty or unreadable table, which
    the caller must treat as "unknown", not as "durable".
    """
    target = PurePosixPath(path)
    best: tuple[str, str] | None = None
    best_depth = -1
    for mount_point, fstype in _iter_mounts(mounts_path):
        candidate = PurePosixPath(mount_point)
        if target != candidate and candidate not in target.parents:
            continue
        depth = len(candidate.parts)
        if depth > best_depth:
            best_depth = depth
            best = (mount_point, fstype)
    return best


def volatile_reason(
    path: str, *, mounts_path: str = DEFAULT_MOUNTS_PATH
) -> str | None:
    """Explain why ``path`` will not survive a reboot, or ``None``.

    ``None`` means "no volatility DETECTED" and is deliberately not
    spelled "durable" -- see the module docstring for the fleet host that
    is durable by filesystem and ephemeral by vendor script.
    """
    found = filesystem_of(path, mounts_path=mounts_path)
    if found is None:
        return None
    mount_point, fstype = found
    if fstype not in VOLATILE_FSTYPES:
        return None
    return (
        f"{path} is on {mount_point} which is {fstype} -- a RAM-backed "
        f"filesystem, so anything written there is lost at the next "
        f"reboot. Applying would converge, report ok, and silently revert; "
        f"a periodic apply-then-check would report ok forever on a host "
        f"that has never once held this configuration."
    )


__all__ = [
    "DEFAULT_MOUNTS_PATH",
    "VOLATILE_FSTYPES",
    "filesystem_of",
    "volatile_reason",
]

# EOF
