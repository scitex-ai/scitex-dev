#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/host_config/_spec.py
"""The HostConfigSpec declaration itself, plus its vocabulary.

Split out of the package __init__ (see GITIGNORED/REFACTORING.md): the
declaration, the federation and the comparison are three separate
responsibilities, and only the first is needed to WRITE a spec.
"""

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

ENTRY_POINT_GROUP = "scitex_dev.host_config"

#: Per-item outcomes of :func:`evaluate`. See the docstring there --
#: ``drift`` is deliberately distinct from ``absent`` because the two
#: warrant opposite responses (converge vs report-and-leave-alone).
STATE_OK = "ok"
STATE_ABSENT = "absent"
STATE_DRIFT = "drift"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_PRECONDITION_UNMET = "precondition_unmet"
STATE_UNREADABLE = "unreadable"

#: Directories holding ADMIN binaries, which are conventionally absent
#: from a normal user's PATH. ``auditctl`` and ``augenrules`` live in
#: ``/usr/sbin`` on Ubuntu, and this host's interactive PATH does not
#: include it -- so a bare ``shutil.which("auditctl")`` returns None on a
#: machine where auditd is installed AND RUNNING, and the spec would
#: report ``precondition_unmet`` forever. Measured on compute-04,
#: 2026-08-12, right after auditd was installed.
_SBIN_DIRS = ("/usr/local/sbin", "/usr/sbin", "/sbin")


@dataclass(frozen=True)
class HostConfigSpec:
    """One file a scitex package requires a HOST to have, verbatim.

    Fields
    ------
    name
        Package-prefixed unique id, e.g. ``"journald.persistent"``.
        Mirrors ``JobSpec.name``: it makes the owning package obvious in
        listings and is the de-duplication key.
    path
        Absolute path of the managed file, e.g.
        ``"/etc/systemd/journald.conf.d/99-scitex-persistent.conf"``.
        Prefer a drop-in directory over editing a distro-owned file: a
        drop-in is additive, removable, and never collides with a
        package upgrade.
    content
        The EXACT desired file body, including the trailing newline.
        Equality against this string is the whole definition of "in
        the declared state" -- there is no partial/merge semantics,
        because a merge cannot be diffed or reasoned about later.
    purpose
        Short human-readable reason, shown in listings and docs. Say
        WHY, not what -- the what is already the content.
    provider
        The declaring package (e.g. ``"scitex-dev"``).
    hosts
        Hostnames this spec applies to. Empty (the default) means EVERY
        host. A non-empty tuple restricts it, and a host outside the
        tuple evaluates to ``not_applicable`` rather than ``absent`` --
        so a laptop-only tweak never shows up as drift on a server.
    mode
        Octal permission string for the file, e.g. ``"0644"``. Checked
        as well as content: a correct file nobody can read is not in
        the declared state.
    apply_command
        Shell command that makes a daemon NOTICE the new file, e.g.
        ``"systemctl restart systemd-journald"``. Run only after the
        file actually changed -- never on a no-op pass, so a periodic
        job does not restart a daemon every time it runs. ``None`` when
        the file is read on demand and no reload is needed.
    verify_command
        Shell command whose OUTPUT demonstrates the config took effect,
        independent of the file's own content. This is the
        anti-tautology field: reading back the file you just wrote
        proves nothing, so a spec that can be observed should say how.
        For journald persistence that is ``journalctl --list-boots``
        (more than one boot listed = the journal demonstrably survived
        a reboot). ``None`` when no observation is available.

        PICK A COMMAND A NORMAL USER CAN RUN. The periodic check is
        unprivileged by design, and a verifier that needs privileges it
        does not have returns a permission error that reads exactly like
        a finding. ``ip -4 -o addr show`` is readable by anyone;
        ``networkctl cat <iface>`` is not, because netplan's generated
        units are 0640 root:systemd-network. When no unprivileged
        equivalent exists, say so with ``verify_requires_root`` rather
        than shipping a command that always fails.
    verify_requires_root
        Whether ``verify_command`` needs root to produce a real answer
        -- ``auditctl -l`` reads the kernel's audit rules and needs
        CAP_AUDIT_CONTROL, so an unprivileged run reports a permission
        error rather than the ruleset. When set and the caller is not
        root, the observation is reported as ``not-observed`` with the
        reason, instead of running the command and recording a failure
        that looks like a finding. Defaults to ``False``.
    requires_root
        Whether writing ``path`` needs root. Defaults to ``True``
        (anything under ``/etc`` does). CHECKING never needs root --
        that asymmetry is why the periodic job can run unprivileged.
    requires_command
        A binary that must exist for this file to MEAN anything, e.g.
        ``"auditctl"`` for a file under ``/etc/audit/rules.d/``. When
        it is absent the spec evaluates to ``precondition_unmet`` and
        ``apply`` refuses to write.

        This exists because the alternative is worse than useless.
        Dropping a rules file onto a host whose daemon is not installed
        produces a file that is present, correct, and read by nothing --
        and every subsequent ``check`` would report ``ok``. That is a
        guard which cannot detect the thing it was installed for, while
        reporting that it can. ``None`` (the default) means the file
        stands on its own.
    """

    name: str
    path: str
    content: str
    purpose: str
    provider: str
    hosts: tuple[str, ...] = ()
    mode: str = "0644"
    apply_command: str | None = None
    verify_command: str | None = None
    verify_requires_root: bool = False
    requires_root: bool = True
    requires_command: str | None = None

    def __post_init__(self) -> None:
        # Fail EARLY at construction, exactly like SystemDepSpec and
        # JobSpec, so a malformed declaration can never reach an
        # applier that is about to write to /etc as root.
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError(
                f"HostConfigSpec.name must be a non-empty id; got {self.name!r}"
            )
        if not isinstance(self.path, str) or not self.path.startswith("/"):
            raise ValueError(
                f"HostConfigSpec({self.name!r}).path must be an ABSOLUTE path; "
                f"got {self.path!r}"
            )
        if not isinstance(self.content, str) or not self.content:
            raise ValueError(
                f"HostConfigSpec({self.name!r}).content must be non-empty -- an "
                f"empty declaration cannot be distinguished from 'no opinion'."
            )
        if not self.content.endswith("\n"):
            # A config file without a trailing newline is a POSIX text-file
            # violation that several parsers silently truncate, and it makes
            # every future diff noisy. Reject at declaration time.
            raise ValueError(
                f"HostConfigSpec({self.name!r}).content must end with a newline."
            )
        if not isinstance(self.provider, str) or not self.provider.strip():
            raise ValueError(
                f"HostConfigSpec({self.name!r}).provider must name the "
                f"declaring package; got {self.provider!r}"
            )
        if not isinstance(self.mode, str) or not self.mode.isdigit():
            raise ValueError(
                f"HostConfigSpec({self.name!r}).mode must be an octal string "
                f"like '0644'; got {self.mode!r}"
            )

    def applies_to(self, hostname: str) -> bool:
        """Whether this spec targets ``hostname``. Empty ``hosts`` = all."""
        return not self.hosts or hostname in self.hosts


