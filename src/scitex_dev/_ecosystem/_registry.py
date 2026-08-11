#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_ecosystem/_registry.py

"""SciTeX ecosystem package registry — *data only*.

SCOPE, STATED FIRST BECAUSE THE NAME IMPLIES OTHERWISE
------------------------------------------------------
``ECOSYSTEM`` is a CURATED SCOPE LIST — the packages in scope for
ecosystem-wide operations. It is **NOT a census of the fleet**, and a
name like ``ECOSYSTEM`` sitting on "the single dict" reads as one.

Four distributions ship, and federate into scitex-dev's own entry-point
groups, while absent from here (measured 2026-07-29): ``scitex-storage``,
``scitex-cards``, ``scitex-linter``, ``scitex-gen``. Entry-point
discovery reads the INSTALLED ENVIRONMENT, not this dict, so a
non-member's declaration reaches the same aggregates a member's does —
one of them reached ``apt-get install`` and detonated a container bake.

So this dict is a valid answer to "what is in scope" and a WRONG answer
to "what exists". Treating it as the second is the documented cause of
that incident and of several sweeps that had to be re-run. See
:func:`scitex_dev._ecosystem._core.get_all_packages` for the full
consumer-facing warning, and card
``ecosystem-registry-is-not-a-complete-fleet-enumeration-20260730`` for
the open question of whether membership should GATE federation (it
would break the four above, including sac).

No curation criteria are recorded anywhere. Absence therefore does not
distinguish "deliberately out of scope" from "nobody added it yet" —
if you add or remove an entry, say why in the commit.

STRUCTURE
---------
This module owns the single ``ECOSYSTEM`` dict and the ``PackageInfo``
schema. It is intentionally pure data so the dependency-aware helpers
(``get_local_path`` / ``should_skip_audit`` / etc. in ``_core.py``)
and the upcoming SSoT generator
(``scitex-dev ecosystem regen-umbrella``, which will derive the
umbrella's ``[all]`` extras, ``lazy_attrs`` map, MCP / CLI mounts
from this same dict) can both consume it without circular imports.

Every public name is re-exported from ``scitex_dev._ecosystem._core``
for backwards compatibility, so existing callers
(``from scitex_dev._ecosystem._core import ECOSYSTEM`` — many) keep
working.
"""

from typing import Dict, TypedDict

from ._registry_data_1 import ECOSYSTEM_PART_1
from ._registry_data_2 import ECOSYSTEM_PART_2


class PackageInfo(TypedDict, total=False):
    """Package information structure.

    ``category`` controls how the auditor and ecosystem CLI treat the
    entry:

    - ``umbrella``     — top-level ``scitex`` package; full audit
    - ``library``      — standard ``scitex-*`` leaf; full audit
    - ``external-lib`` — non-scitex-prefixed lib (figrecipe, socialia,
                          newb); full audit
    - ``template``     — scaffolds; auditor skips §C5/§E/§L by default
    - ``dataset``      — data-only repos (crossref-local, openalex-local);
                          auditor skips §E (no SKILL.md required)

    ``archived`` (optional, default False) — set ``True`` for repos
    that have been GitHub-archived (read-only) and superseded. The
    CLA / quality / publish auditors short-circuit on archived; the
    entry stays in the registry so historical refs resolve.

    ``umbrella_subcommand`` (optional) — the name this package mounts
    as under the umbrella ``scitex`` CLI / MCP server. For
    ``scitex-<x>`` the default is the part after ``scitex-`` (so
    ``scitex-dataset`` → ``dataset``). Branded packages without the
    prefix (``socialia`` → ``social``, ``figrecipe`` → ``plt``) MUST
    set this explicitly; the umbrella shim and ``audit-cli §5b`` /
    ``audit-mcp-tools §1`` read it to know how to rewrite the program
    name and validate the mount namespace. See
    ``_skills/general/03_interface/02_cli/05a_umbrella-passthrough.md``.

    Umbrella SSoT fields (optional, all consumed by
    ``scitex_dev._ecosystem._umbrella``; defaults are *derived* from
    ``import_name`` so most entries don't need to set them):

    - ``umbrella_lazy_short`` — the ``scitex.<short>`` lazy-module
      alias name. Default = ``import_name.removeprefix("scitex_")``.
      Set explicitly for branded packages (``socialia`` → ``"social"``,
      ``figrecipe`` → ``"fig"``).
    - ``umbrella_extra`` — the ``scitex[<extra>]`` extra-group name
      shipped in the umbrella's ``[project.optional-dependencies]``.
      Default = ``umbrella_lazy_short`` (same name as the alias). Set
      explicitly when the extra name differs from the alias.
    - ``umbrella_external`` — the peer import target used in
      ``EXTERNAL_REEXPORTS`` (the lazy-loader bridge that makes
      ``import scitex.<short>.<sub>`` resolve to the peer standalone).
      Default = ``import_name`` (e.g. ``scitex_io``). Set explicitly
      when the umbrella alias points at a *sub*-module of the peer
      (e.g. ``media`` → ``"scitex_etc.media"``).
    - ``umbrella_core_dep`` — ``True`` iff this peer is pinned in the
      umbrella's core ``dependencies`` (always installed), not just an
      optional extra. Default ``False``.
    - ``umbrella_skip`` — ``True`` iff this entry should NOT be auto-
      mounted by the SSoT generator (e.g. ``scitex-dev`` itself is
      installed but exposes no ``scitex.dev`` lazy_attr beyond the
      in-tree shim; optional peers like ``scitex-hub`` are mounted
      via the auxiliary ``_umbrella.AUX_MOUNTS`` table instead so
      ``[all]`` can deliberately exclude them). Default ``False``.
    """

    local_path: str
    pypi_name: str
    github_repo: str
    import_name: str
    category: str
    archived: bool
    umbrella_subcommand: str
    umbrella_lazy_short: str
    umbrella_extra: str
    umbrella_external: str
    umbrella_core_dep: bool
    umbrella_skip: bool


# Ordered dict — order matters for display. The literal entries live in
# ``_registry_data_1`` / ``_registry_data_2`` (split only for the
# 512-line file cap); the concatenation below preserves display order
# and the part key sets are disjoint (both invariants are pinned by
# ``tests/scitex_dev/_ecosystem/test__registry.py``).
ECOSYSTEM: Dict[str, PackageInfo] = {**ECOSYSTEM_PART_1, **ECOSYSTEM_PART_2}


__all__ = ["ECOSYSTEM", "PackageInfo"]


# EOF
