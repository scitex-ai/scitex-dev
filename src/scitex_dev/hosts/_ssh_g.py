#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Asking ssh what it would actually do — the reader half of the drift check.

Split from :mod:`._effective` on a real seam, the same one ``_registry`` and
``_parse`` use: THIS module changes when ssh's invocation or output format
changes; ``_effective`` changes when the CHECK's policy does.

``ssh -G`` resolves configuration and exits without connecting, so everything
here is safe to run against a machine that is switched off — and it is the
only honest reader of an ssh config, because it is ssh answering about
itself. A human reading the file can be wrong about which stanza wins;
measured 2026-08-13, an ``Include`` on line 1 silently beat every stanza
below it.

TELLING A DECLARED KEY FROM ONE OF SSH'S BUILT-IN DEFAULTS
-----------------------------------------------------------
``ssh -G`` lists the built-in identity candidates (``~/.ssh/id_rsa``,
``id_ecdsa``, ``id_ed25519``, ...) whether or not any config mentioned them,
and most of those files legitimately do not exist. Flagging all seven would
bury the one that matters.

The obvious discriminator — subtract the default set — is WRONG, and wrong
precisely on the case this exists to catch: scitex-compute-01's stanza named
``~/.ssh/id_rsa``, which is ITSELF one of the built-in defaults, so
subtraction erases it and the check reports nothing. That was measured, not
reasoned about: the first implementation passed every test except the one
reproducing the real incident.

What actually distinguishes them is REPLACEMENT, also measured (OpenSSH 9.6)::

    a stanza declaring one IdentityFile  ->  ssh -G reports exactly 1 line
    a stanza declaring none              ->  ssh -G reports all 7 defaults

A declared set REPLACES the defaults rather than adding to them, so the test
is list INEQUALITY against :func:`builtin_identity_files` — obtained with
``-F /dev/null``, genuinely config-free, unlike a sentinel NAME, which a
``Host *`` stanza would still match.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from ._run import run_command, ssh_base_argv

__all__ = [
    "BASELINE_SENTINEL",
    "builtin_identity_files",
    "effective_config",
    "expand_identity_path",
    "identity_exists",
    "parse_ssh_g",
]

#: The name used to ask ssh about its own defaults. ``.invalid`` is reserved
#: by RFC 2606 and can never resolve, so even a fat-fingered run (one without
#: ``-G``) cannot connect to anything.
BASELINE_SENTINEL = "scitex-dev-baseline-probe.invalid"


def parse_ssh_g(text: str) -> dict[str, list[str]]:
    """Parse ``ssh -G`` output into ``{lowercase key: [values]}``.

    Values are kept as a LIST for every key, not just the repeatable ones.
    ``identityfile`` legitimately repeats, and a parser that stored a scalar
    for it would silently keep whichever line happened to be last — which is
    ssh's LOWEST-priority candidate, the opposite of what a caller wants.
    """
    out: dict[str, list[str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key, _, value = line.partition(" ")
        key = key.strip().lower()
        if not key:
            continue
        out.setdefault(key, []).append(value.strip())
    return out


def _ssh_g_argv(alias: str, *, config_file) -> list[str]:
    argv = ["ssh", "-G"]
    if config_file is not None:
        argv += ["-F", str(config_file)]
    argv.append(alias)
    return argv


def through(hop: str | None, argv: list[str], *, connect_timeout: int) -> list[str]:
    """Run ``argv`` locally, or THROUGH ``hop`` when one is given."""
    if hop is None:
        return argv
    return ssh_base_argv(connect_timeout=connect_timeout) + [hop, shlex.join(argv)]


def effective_config(
    alias: str,
    *,
    runner=run_command,
    config_file: str | Path | None = None,
    hop: str | None = None,
    timeout: float = 15.0,
    connect_timeout: int = 5,
) -> dict[str, list[str]] | None:
    """Ask ssh what it would ACTUALLY use for ``alias``. ``None`` on failure.

    ``hop`` runs the question on ANOTHER machine, which is the only way to
    learn what a peer's own config says — the compute-01 fault lived in
    compute-01's file, not in ours.
    """
    argv = through(
        hop, _ssh_g_argv(alias, config_file=config_file),
        connect_timeout=connect_timeout,
    )
    result = runner(argv, timeout=timeout)
    if not result.ok:
        return None
    return parse_ssh_g(result.stdout)


def expand_identity_path(path: str, *, home: Path) -> Path:
    """Expand ssh's ``~`` and ``%d`` tokens against ``home``.

    Against the PASSED home, never ``Path.expanduser()``'s. ``ssh -G`` emits
    identity paths unexpanded (measured, OpenSSH 9.6: ``identityfile
    ~/.ssh/id_rsa``), and when the answer came from a peer via ``hop`` the
    ``~`` is THAT machine's home. Expanding it against ours would check the
    wrong filesystem and report a key present or missing on a machine that
    was never consulted.
    """
    if path == "~":
        return home
    if path.startswith("~/"):
        return home / path[2:]
    return Path(path.replace("%d", str(home)))


def builtin_identity_files(
    *, runner=run_command, hop=None, timeout: float = 15.0, connect_timeout: int = 5
) -> tuple[str, ...]:
    """ssh's COMPILED-IN identity candidates, read with no user config at all.

    ``-F /dev/null`` rather than the checked config: a ``Host *`` stanza
    matches every name including the sentinel, so a baseline taken through
    the user's own config would silently absorb a globally declared key and
    then never report it missing.

    An EMPTY result means the baseline could not be established. A caller
    must NOT read that as "nothing was declared" — see
    ``SshConfigReport.baseline_available``.
    """
    resolved = effective_config(
        BASELINE_SENTINEL,
        runner=runner,
        config_file=os.devnull,
        hop=hop,
        timeout=timeout,
        connect_timeout=connect_timeout,
    )
    if resolved is None:
        return ()
    return tuple(resolved.get("identityfile", []))


def identity_exists(
    raw: str, *, runner, hop, home: Path, timeout: float, connect_timeout: int
) -> bool:
    """Is the identity file at ``raw`` present on the machine being checked?

    Locally that is a stat. Remotely it is ``test -r`` run by THAT machine's
    shell, with ``~`` handed over as ``$HOME`` so the REMOTE home expands —
    the whole question is about the peer's filesystem, and resolving the path
    here would answer about ours.
    """
    if hop is None:
        return expand_identity_path(raw, home=home).exists()
    remote = raw.replace("%d", "$HOME")
    if remote.startswith("~"):
        remote = "$HOME" + remote[1:]
    argv = ssh_base_argv(connect_timeout=connect_timeout) + [
        hop,
        f'test -r "{remote}"',
    ]
    return runner(argv, timeout=timeout).ok


# EOF
