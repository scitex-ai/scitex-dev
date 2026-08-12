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


#: Audit rules that answer ONE question: who ended this process?
#:
#: Scoped to that question on purpose. A general-purpose audit policy is
#: noisy, and a noisy ruleset gets switched off by the first person it
#: inconveniences -- leaving a declaration that is present and worthless.
#:
#: Two rule families, because NEITHER ALONE IS SUFFICIENT, and the reason
#: is a measured property of this host rather than a guess:
#:
#: 1. `kill` IS A SHELL BUILTIN (verified on scitex-compute-04:
#:    `type kill` -> "kill is a shell builtin"). So `kill -9 <pid>` typed
#:    at a prompt performs NO execve whatsoever. Only the syscall rule
#:    sees it.
#: 2. `tmux kill-server` ends the server from INSIDE the server -- the
#:    client hands the command over the socket and the server acts on
#:    itself. Whatever signal record that produces carries the SERVER's
#:    credentials, not the human's. Only the CLIENT's execve record
#:    carries the loginuid, tty and session of whoever asked.
#:
#: What this CANNOT do, stated plainly so nobody mistakes its silence for
#: an all-clear: it records WHO, not WHETHER-IT-WAS-REASONABLE. A kill
#: from a process the operator ran himself is recorded identically to any
#: other -- that judgement is a human's. It also cannot see a process that
#: exits of its own accord (a crash leaves a coredump record instead), and
#: it says nothing about 32-bit binaries (arch=b32 rules are omitted: this
#: is a 64-bit fleet and doubling the ruleset for that would be noise).
#:
#: auid is the loginuid -- the identity of the login session, preserved
#: across su/sudo/setuid. `auid!=4294967295` excludes kernel/system
#: contexts with no login session. The numeric form is used rather than
#: the friendlier `unset` alias because the alias is not accepted by
#: older auditctl, and this file has to load on whatever version a host
#: happens to ship.
AUDITD_PROCESS_KILL = """\
# Managed by scitex-dev. Do not edit by hand -- edits show up as DRIFT in
# `scitex-dev ecosystem host-config check` and are deliberately NOT
# auto-reverted. On a security-audit config that restraint matters most:
# someone may have tuned this on purpose, and silently reverting it would
# be worse than the drift.
#
# Declared by HostConfigSpec "auditd.process-kill" in
# scitex_dev/host_config/_declarations.py. To change this file, change that
# declaration and let the job apply it.
#
# WHY: see the incident recorded on card hostconfig-federation-journald.
# The short version is that a process died, every alternative cause was
# excluded from the journal, and the host recorded nothing that could say
# who ended it. These rules record exactly that and little else.

## 1. Who signalled whom, for the three signals that end a process.
##    `kill` is a shell BUILTIN, so `kill -9 <pid>` emits no execve at
##    all -- this is the only rule that sees it. a1 is the signal
##    number: 1 SIGHUP, 9 SIGKILL, 15 SIGTERM.
-a always,exit -F arch=b64 -S kill,tkill,tgkill -F a1=1 -F auid>=1000 -F auid!=4294967295 -k scitex_signal
-a always,exit -F arch=b64 -S kill,tkill,tgkill -F a1=9 -F auid>=1000 -F auid!=4294967295 -k scitex_signal
-a always,exit -F arch=b64 -S kill,tkill,tgkill -F a1=15 -F auid>=1000 -F auid!=4294967295 -k scitex_signal

## 2. Who ran a process-killing tool. `tmux kill-server` acts on the
##    server from inside it, so the signal record carries the server's
##    credentials rather than the human's; the client's execve is the
##    only record that carries the loginuid, tty and session of whoever
##    asked. The argv is captured in the EXECVE record, so
##    `kill-server` is distinguishable from an ordinary attach at read
##    time -- audit cannot filter on argv, which is why every tmux
##    invocation is recorded. That is the one rule here with real
##    volume, and it is the rule aimed squarely at the open question.
-a always,exit -F arch=b64 -S execve -F exe=/usr/bin/tmux -F auid>=1000 -F auid!=4294967295 -k scitex_killer_exec
-a always,exit -F arch=b64 -S execve -F exe=/usr/bin/pkill -F auid>=1000 -F auid!=4294967295 -k scitex_killer_exec
-a always,exit -F arch=b64 -S execve -F exe=/usr/bin/killall -F auid>=1000 -F auid!=4294967295 -k scitex_killer_exec

## Read them back with:
##   ausearch -k scitex_signal -i
##   ausearch -k scitex_killer_exec -i
"""


def provide() -> list[HostConfigSpec]:
    """Host-level configuration scitex-dev itself requires."""
    # The DHCP requested-address drop-ins live in `hosts/` rather than
    # beside this file, and the placement is deliberate on two counts.
    # Topically, they RENDER the fleet address map that `hosts` owns --
    # one spec per machine, each carrying an address the registry
    # declares -- so they belong with the registry rather than with a
    # literal constant. Structurally, a fourth `_host_config*.py` at the
    # package root would extend the `host_*` prefix cluster PS-108
    # already reports here, and push the flat-file count past PS-108b's
    # threshold.
    from ..hosts._dhcp import provide_dhcp_specs

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
        HostConfigSpec(
            name="auditd.process-kill",
            path="/etc/audit/rules.d/99-scitex-process-kill.rules",
            content=AUDITD_PROCESS_KILL,
            purpose=(
                "Record WHO signalled a process and WHO ran a "
                "process-killing tool, so a death like the one on card "
                "hostconfig-federation-journald is attributable instead "
                "of merely observed. Needs the auditd package: "
                "`apt-get install auditd`."
            ),
            provider="scitex-dev",
            # World-readable ON PURPOSE, against the usual 0640 hardening
            # habit. The content is in this repo, so restricting the
            # on-host copy conceals nothing that is not already in git --
            # while 0640 would make the unprivileged `check` fail to read
            # it and report drift on a perfectly converged host. The
            # honest self-report is worth more than the pretence.
            mode="0644",
            # augenrules compiles rules.d into /etc/audit/audit.rules and
            # loads it. Preferred over restarting auditd, which is
            # refused outright on some systems and is heavier than the
            # job needs.
            apply_command="augenrules --load",
            # OBSERVATION: the rules that are actually LIVE IN THE
            # KERNEL. Reading the file back would only prove the file was
            # written -- `auditctl -l` proves the kernel accepted it,
            # which is the thing that has to be true.
            verify_command="auditctl -l",
            # `auditctl -l` reads the kernel's audit rules and needs
            # CAP_AUDIT_CONTROL. There is no unprivileged equivalent --
            # reading the rules FILE back would only prove the file was
            # written, which is the tautology verify_command exists to
            # avoid. So the unprivileged timer reports `not-observed`
            # with the reason rather than a permission error that reads
            # like the ruleset having vanished.
            verify_requires_root=True,
            requires_root=True,
            # Without auditd, this file is read by nothing. Declaring the
            # precondition makes the gap REPORTABLE rather than papering
            # over it with a correct-looking file that silently answers
            # `ok` forever.
            requires_command="auditctl",
        ),
        *provide_dhcp_specs(),
    ]


__all__ = ["AUDITD_PROCESS_KILL", "JOURNALD_PERSISTENT", "provide"]

# EOF
