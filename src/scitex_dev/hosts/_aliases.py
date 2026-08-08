#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Host ALIASES — the separation between a logical label and a hostname.

Why this exists
---------------
The registry key is the name the fleet uses for a machine. It was also,
by accident, the only name a machine could be found by. That forced two
unrelated decisions to be the same decision:

* what we CALL the machine (a logical label: ``scitex-laptop-01``), and
* what the machine calls ITSELF, or what an ssh config calls it
  (``ywata-note-win``, ``mba``, ``scitex-03``).

The operator's constraint is exactly that these must come apart —
"ホストネームと論理的なラベルは分けたいところ", i.e. give a machine a fleet
label WITHOUT touching its hostname. Renaming a key alone cannot do
that: it silently un-resolves every caller that still says the old name,
and :func:`~scitex_dev.hosts.resolve` fails loud by design, so the
breakage is immediate and total.

Aliases make the rename SAFE: the key becomes the logical label, the old
name stays resolvable as an alias, and ``hostname_reported`` records what
the OS answers. Three fields, three different questions.

Fails loud, never silently prefers
----------------------------------
An alias that could mean two machines is not a lookup problem, it is a
DATA problem, and resolving it by some precedence rule would hand the
caller a plausible wrong host. That is the failure this registry exists
to prevent: a name that silently resolves to the wrong box is how an
agent ends up configuring, or wiping, a machine it never meant to touch.
So :func:`build_alias_index` refuses to build an ambiguous index at all.

The one case that is NOT an error: a host listing its own key as an
alias. It is redundant, it resolves to the same machine either way, and
rejecting it would punish a config that is merely verbose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from .._core.errors import ErrorCode

__all__ = ["build_alias_index", "parse_aliases"]


def parse_aliases(name: str, raw, *, hosts_path: Path) -> tuple[str, ...]:
    """Parse one host's ``aliases:`` block into a tuple of names.

    Shape: a list of strings. Absent / ``null`` / ``[]`` means the host
    has no alternative names, which is the common case and is NOT an
    error.

    A bare string (``aliases: mba``) is REJECTED rather than wrapped.
    YAML makes that typo easy and the wrapped reading is not obviously
    what was meant — someone writing ``aliases: mba, nas`` would get one
    alias literally named ``"mba, nas"``. Better to say so.
    """
    from ._registry import HostRegistryError

    if raw is None:
        return ()
    if isinstance(raw, str) or not isinstance(raw, list):
        raise HostRegistryError(
            f"{hosts_path}: host {name!r}: `aliases` must be a LIST of names, "
            f"got {type(raw).__name__} {raw!r}",
            code=ErrorCode.VALIDATION,
            remediation=(
                "Write it as a list, e.g.\n"
                "  aliases:\n"
                "    - ywata-note-win\n"
                "    - ywata"
            ),
        )
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise HostRegistryError(
                f"{hosts_path}: host {name!r}: each alias must be a string, got "
                f"{type(entry).__name__} {entry!r}",
                code=ErrorCode.VALIDATION,
                remediation="Quote the value if YAML is reading it as a number or bool.",
            )
        alias = entry.strip()
        if not alias:
            raise HostRegistryError(
                f"{hosts_path}: host {name!r}: empty alias",
                code=ErrorCode.VALIDATION,
                remediation="Delete the empty entry. An empty name resolves nothing.",
            )
        if alias not in out:
            out.append(alias)
    return tuple(out)


def build_alias_index(
    records: Mapping[str, "object"], *, hosts_path: Path
) -> dict[str, str]:
    """Map every alias to its host name, refusing anything ambiguous.

    Two collisions are rejected, both because the alternative is
    answering a question that has two right answers:

    * an alias claimed by TWO hosts;
    * an alias that is another host's registry KEY — the key must always
      win as itself, so the alias could never be honoured and pretending
      otherwise hides a real conflict.

    A host aliasing its OWN key is fine and is dropped from the index (a
    key lookup already finds it).
    """
    from ._registry import HostRegistryError

    index: dict[str, str] = {}
    for host_name, record in records.items():
        for alias in getattr(record, "aliases", ()) or ():
            if alias == host_name:
                continue
            if alias in records:
                raise HostRegistryError(
                    f"{hosts_path}: host {host_name!r} claims alias {alias!r}, "
                    f"which is another host's registry key",
                    code=ErrorCode.VALIDATION,
                    remediation=(
                        f"A key always resolves to itself, so this alias could "
                        f"never win. Remove {alias!r} from {host_name!r}'s "
                        f"aliases, or rename one of the two hosts."
                    ),
                )
            owner = index.get(alias)
            if owner is not None and owner != host_name:
                first, second = sorted((owner, host_name))
                raise HostRegistryError(
                    f"{hosts_path}: alias {alias!r} is claimed by both "
                    f"{first!r} and {second!r}",
                    code=ErrorCode.VALIDATION,
                    remediation=(
                        f"An alias names exactly one machine. Remove {alias!r} "
                        f"from whichever of {first!r} / {second!r} should not "
                        f"answer to it."
                    ),
                )
            index[alias] = host_name
    return index


def resolve_via_alias(
    name: str, records: Mapping[str, "object"], *, hosts_path: Path
) -> str | None:
    """Return the host NAME that ``name`` aliases, or ``None``.

    Deliberately returns the key rather than the record, so the caller
    keeps one lookup path (``records[key]``) and the alias layer stays a
    pure name-to-name mapping.
    """
    return build_alias_index(records, hosts_path=hosts_path).get(name)


def known_names(records: Mapping[str, "object"]) -> Iterable[str]:
    """Every name that resolves: registry keys plus all aliases.

    Used for the "did you mean" listing on an unknown host, so an alias
    the caller could legitimately have used is not omitted from the very
    error that lists the valid options.
    """
    names = set(records)
    for record in records.values():
        names.update(getattr(record, "aliases", ()) or ())
    return sorted(names)


# EOF
