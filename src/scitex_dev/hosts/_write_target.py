# -*- coding: utf-8 -*-
"""Where a WRITE to ``hosts.yaml`` is allowed to land.

Reads and writes need different answers here, and conflating them is what
this module exists to stop.

The failure it kills
--------------------
``get_hosts_yaml_path()`` resolves through ``Path.home()``. Inside an agent
container ``$HOME`` is ``/home/agent`` while the fleet's registry lives under
the operator's home, so a write from a container lands in a private copy that
NO reader on the host ever opens — and every layer reports success. Measured
2026-08-05: ``sac host add`` did exactly this, `sac host validate` said "ok,
2 peer(s)" about the shadow, and the rows were reported to the operator as
registered when nothing had been registered.

The two files make this very hard to notice:

    /home/ywatanabe/.scitex/dev/hosts.yaml   inode 1253677   mtime 07-29
    /home/agent/.scitex/dev/hosts.yaml       inode 5459493   mtime 07-18
    md5: IDENTICAL

Every CONTENT check — diff, md5, "is the registry correct?" — reports
agreement. The discriminator is IDENTITY, not bytes. They agree only because
nobody has edited either one; the first write is what makes them diverge, and
by then the write has already gone to the wrong place.

It is worse than "unread", too: the operator's ``~/.scitex`` is a symlink into
``~/.dotfiles/src/.scitex``, so the real registry is a TRACKED file, while the
shadow is an ordinary untracked directory. A row written there is unread,
uncommitted, unreviewed, and invisible to the agent that owns that tree.

Why AMBIGUITY, not container-detection
--------------------------------------
The obvious fix — "detect that we are in a container and rewrite the path" —
needs a reliable container signal and a hardcoded operator username. Both are
guesses that rot.

The honest signal is already present and needs neither: when more than one
plausible registry is VISIBLE, the process cannot know which one the fleet
reads, so it must not pick. Counting candidates is direction-independent —
it flags the case where the shadow is newer just as readily as where it is
older, and it flags the case where the two agree byte-for-byte, which is
exactly the state that hid this for eleven days.

On the operator's own machine only one home exists, so there is one candidate
and writes proceed untouched. In a container both are mounted, so there are
two and the write refuses with both paths named.

WHO CAN ACTUALLY WRITE, THEN
----------------------------
Read this before treating a refusal as a bug: **no containerized agent can
write the registry by the default path.** That is the intended consequence,
not an oversight — but it means the work must move rather than stop, and the
error says where to. Measured on the bare host (scitex-hpc, 2026-08-05):

    PRESENT   /home/ywatanabe/.scitex/dev/hosts.yaml   inode 1253677
    ABSENT    /home/agent/...   — `/home/agent` does not exist there at all

So on the host exactly one registry is visible and the write proceeds
untouched. The shadow is purely a container artifact, and it is PER
CONTAINER: two agents measured different inodes and mtimes for their own
copies. No shadow is authoritative and no two agree.

Doing the write from the bare host (host-exec) is therefore preferred over
setting the env var: it SATISFIES this check by its normal rule rather than
overriding it — the write happens where the ambiguity genuinely does not
exist. The override is better suited to tests and to hosts with a
non-standard layout.

Worth knowing, and deliberately not acted on: a container's
``/home/ywatanabe`` is a BIND MOUNT of the real file — same inode, 1253677,
from inside and outside. A write there WOULD land correctly. The guard still
refuses, because the refusal is not "this path is wrong", it is "the writer
cannot prove which of the two is right". Refusing on ambiguity rather than on
a guess is the conservative direction and does not depend on knowing the
mount topology, which a process cannot portably discover.

KNOWN BOUND, stated rather than papered over: a container that does NOT mount
the operator's home sees exactly one candidate and is allowed to write to it.
Nothing visible to the process distinguishes that from a single-home host.
The remedy there is the same env var — set ``SCITEX_DEV_HOSTS_YAML`` in the
container spec and the question never arises.
"""

from __future__ import annotations

import os
from pathlib import Path

from ._registry import HostRegistryError, get_hosts_yaml_path

#: Same override `get_hosts_yaml_path` honours. An explicit answer always
#: wins over this module's guessing, because a deployment that has been told
#: where the registry lives is not ambiguous.
_ENV_HOSTS_YAML = "SCITEX_DEV_HOSTS_YAML"

#: Where home directories live. A PARAMETER with this default rather than a
#: module constant, so a test points it at real directories it built instead
#: of rewriting this module's internals — the collaborator is injected, which
#: is also what STX-NM002 requires.
DEFAULT_HOMES_ROOT = Path("/home")

#: Path of a registry relative to a home directory.
_REL = Path(".scitex") / "dev" / "hosts.yaml"


def candidate_hosts_yamls(homes_root: str | Path | None = None) -> list[Path]:
    """Every registry file VISIBLE to this process, sorted.

    Home directories are ENUMERATED rather than assumed, so no operator
    username is baked into the package.

    Only files that actually exist count. A home directory without a registry
    is not a candidate — it is somewhere a registry could go, which is not the
    same as somewhere the fleet reads. Counting empty homes would refuse
    writes on ordinary multi-user machines.
    """
    root = Path(homes_root) if homes_root is not None else DEFAULT_HOMES_ROOT
    if not root.is_dir():
        return []
    try:
        homes = sorted(root.iterdir())
    except OSError:
        return []
    found: list[Path] = []
    for home in homes:
        candidate = home / _REL
        try:
            if candidate.is_file():
                found.append(candidate)
        except OSError:
            continue
    return found


def resolve_hosts_yaml_for_write(
    hosts_path: str | Path | None = None,
    *,
    homes_root: str | Path | None = None,
) -> Path:
    """Resolve where a write may land, or REFUSE.

    Precedence, highest first:

    1. an explicit ``hosts_path`` — the caller has stated the target;
    2. ``$SCITEX_DEV_HOSTS_YAML`` — the deployment has stated the target;
    3. the ordinary resolution, but ONLY when it is unambiguous.

    Raises
    ------
    HostRegistryError
        When more than one registry is visible and nothing has said which is
        canonical. The message names every candidate and the variable that
        settles it, because an error that only says "ambiguous" leaves the
        reader exactly where they started.
    """
    if hosts_path is not None:
        return Path(hosts_path).expanduser()

    env_override = os.environ.get(_ENV_HOSTS_YAML, "").strip()
    if env_override:
        return Path(env_override).expanduser()

    resolved = get_hosts_yaml_path()
    candidates = candidate_hosts_yamls(homes_root)
    if len(candidates) <= 1:
        return resolved

    listed = "\n".join(f"    {p}" for p in candidates)
    raise HostRegistryError(
        f"refusing to write the host registry: {len(candidates)} registries "
        f"are visible from here and nothing says which one the fleet reads.\n"
        f"{listed}\n"
        f"  would have written: {resolved}\n"
        "This is the container-shadow trap: $HOME differs inside an agent "
        "container, so the write lands in a private copy that no reader on "
        "the host opens, and every layer reports success. Note the files may "
        "be byte-identical — content checks agree; only identity "
        "distinguishes them.\n"
        "You are almost certainly in an agent container. Two ways forward, "
        "in preference order:\n"
        "  1. Perform the write ON THE BARE HOST (e.g. via host-exec), where "
        "only one registry is visible and this check permits it by its "
        "normal rule. That satisfies the guard rather than bypassing it — "
        "the write happens where the ambiguity does not exist.\n"
        f"  2. Set {_ENV_HOSTS_YAML} to the registry the fleet reads (for a "
        "sac agent container, in the container spec), or pass an explicit "
        "path. An explicit answer is not a guess, which is why it is "
        "honoured.\n"
        "Do NOT 'just pick the newest' — mtime is not authority."
    )


__all__ = [
    "DEFAULT_HOMES_ROOT",
    "candidate_hosts_yamls",
    "resolve_hosts_yaml_for_write",
]

# EOF
