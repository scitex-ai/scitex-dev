#!/usr/bin/env python3
# Timestamp: 2026-06-07
# File: scitex_dev/_ecosystem/_core.py

"""SciTeX ecosystem helpers — local-path resolution + audit-skip policy.

The package registry itself (``PackageInfo`` schema + ``ECOSYSTEM``
dict) lives in the sibling ``_registry`` module so the data table and
the helpers can grow independently and stay under the line-limit
hook. Both names are re-exported here so every existing
``from scitex_dev._ecosystem._core import ECOSYSTEM`` import keeps
working unchanged.
"""

from pathlib import Path
from typing import List, Optional

from ._registry import ECOSYSTEM, PackageInfo

__all__ = [
    "ECOSYSTEM",
    "PackageInfo",
    "get_all_packages",
    "get_local_path",
    "should_skip_audit",
    "is_mcp_mountable",
    "mountable_peers",
]


def get_local_path(package: str) -> Optional[Path]:
    """Get expanded local path for a package."""
    if package not in ECOSYSTEM:
        return None
    return Path(ECOSYSTEM[package]["local_path"]).expanduser()


def get_all_packages() -> List[str]:
    """Registered ecosystem package names — a CURATED SCOPE, not a census.

    NOT A COMPLETE ENUMERATION OF THE FLEET. This returns exactly the
    packages someone added to ``ECOSYSTEM``. Distributions can exist,
    ship, and FEDERATE INTO SCITEX-DEV'S OWN ENTRY-POINT GROUPS while
    absent from it — measured 2026-07-29, four of them: scitex-storage,
    scitex-cards, scitex-linter, scitex-gen.

    Do not use this as a DENOMINATOR for "the fleet". It answers "which
    packages are in scope for ecosystem-wide operations", which is a
    different question and a smaller set.

    The cost of the other reading is on record. scitex-storage is not a
    member, declares a `system_deps` entry point, and entry-point
    discovery reads the INSTALLED ENVIRONMENT rather than this dict — so
    its `fclones` declaration reached `apt-get install` and detonated a
    container bake that nothing here could have predicted. Anyone
    auditing "who declares system deps" from this function would have
    answered 4 when the answer was 5.

    Two enumeration sources exist and they have OPPOSITE blind spots:

        entry points  ->  only what is INSTALLED in the calling env
        ECOSYSTEM     ->  only what was DECLARED a member

    Neither is complete, and reaching for the more official-looking one
    is what produced the miss. For a real census use `gh repo list
    scitex-ai`, or enumerate entry points from the environment you
    actually care about.

    Nothing records WHY a given package is in or out — there are no
    written curation criteria — so absence from this dict does not
    distinguish "deliberately out of scope" from "nobody added it yet".
    Whether membership should GATE federation is open
    (ecosystem-registry-is-not-a-complete-fleet-enumeration-20260730);
    it would break the four distributions above, including sac, so it is
    not a change to make casually.
    """
    return list(ECOSYSTEM.keys())


# --------------------------------------------------------------------- #
# Category-aware audit skip                                              #
# --------------------------------------------------------------------- #

# Per-auditor list of ECOSYSTEM categories that don't apply.
# ``archived`` is short-circuited separately (every auditor skips
# archived).
_CATEGORY_SKIP: dict[str, frozenset[str]] = {
    "audit-cli": frozenset({"template"}),
    "audit-mcp-tools": frozenset({"template", "dataset", "umbrella"}),
    "audit-skills": frozenset(),
    "audit-python-apis": frozenset({"template"}),
    "audit-project": frozenset(),
}


# --------------------------------------------------------------------- #
# MCP aggregator mount policy                                           #
# --------------------------------------------------------------------- #

# Packages that ship a ``_mcp_server`` FastMCP instance but must NOT be
# auto-mounted onto the umbrella MCP aggregator (``scitex serve`` /
# ``scitex-mcp-server``; see ``scitex._mcp.register_all_tools`` ->
# ``_iter_registry``). This is the single source of truth the aggregator
# consults via :func:`is_mcp_mountable` / :func:`mountable_peers`.
#
# - ``scitex-orochi`` is the single-instance agent-communication
#   ORCHESTRATOR. Its ``mcp_server`` module is guarded to ``sys.exit`` /
#   refuse when a Telegram bot token or telegram agent-role is present,
#   and it is NOT a per-agent tool provider. Mounting it is both
#   semantically wrong AND a cold-start hazard (its import blocks the
#   aggregator's serial peer-resolution loop), so it is skipped
#   unconditionally.
# - ``scitex-types`` ships NO ``_mcp_server`` (it exposes ZERO MCP tools)
#   yet importing the package pulls the heavy scientific stack
#   (numpy / optionally torch / xarray / pandas via ``_ArrayLike``). The
#   aggregator's peer-resolution imports the package while probing for a
#   FastMCP instance that does not exist — pure cold-start waste with no
#   tool payoff — so it is skipped.
# - ``scitex-str`` likewise ships NO ``_mcp_server`` / ``mcp_server`` /
#   ``_mcp`` (ZERO MCP tools — it is a pure text-utility library). Probing
#   it still imports ``scitex_str``, which eagerly pulls pandas + numpy via
#   its ``_search`` / ``_plot`` submodules (~1.4 s cold, inflating toward
#   the per-peer timeout in a fresh SIF). No FastMCP instance exists to
#   mount, so — exactly like ``scitex-types`` — it is pure cold-start waste
#   and is skipped. (Diagnosed in sac's real-SIF re-verify of umbrella
#   2.30.8.)
#
# Distinct from ``umbrella_skip`` (a per-entry registry field that only
# gates the Python-API SSoT / ``[all]`` extras generator, NOT the MCP
# mount) and from ``archived`` / ``_SKIP_CATEGORIES`` (already honoured
# aggregator-side). A package may ALSO opt out per-entry by setting
# ``"mcp_mountable": False`` in its ``ECOSYSTEM`` record; both signals
# are honoured.
#
# NOTE: ``scitex-resource`` is deliberately NOT skipped here — it ships
# real tools (``get_specs`` / ``get_metrics`` / …). Its cold-start hazard
# (a demo-only top-level ``import matplotlib.pyplot`` that triggered the
# font-cache build) is fixed at the source in scitex-resource by deferring
# that import into the ``__main__`` block, so it stays mounted and cheap.
_MCP_UNMOUNTABLE: frozenset = frozenset(
    {"scitex-orochi", "scitex-types", "scitex-str"}
)


def is_mcp_mountable(package: str) -> bool:
    """Return ``True`` iff ``package`` may be auto-mounted onto the umbrella MCP.

    A package is NOT mountable when any of the following hold:

    - it is unknown to the registry (fail closed — nothing to mount),
    - its ``ECOSYSTEM`` record is ``archived``,
    - its ``category`` is one the aggregator never mounts
      (``umbrella`` / ``template``),
    - its record sets ``"mcp_mountable": False``,
    - it is listed in :data:`_MCP_UNMOUNTABLE`.

    This is the SSoT the umbrella aggregator consults so the skip policy
    lives in one place (scitex-dev), not duplicated in scitex-python.
    """
    info = ECOSYSTEM.get(package)
    if info is None:
        return False
    if info.get("archived"):
        return False
    if info.get("category") in {"umbrella", "template"}:
        return False
    if info.get("mcp_mountable") is False:
        return False
    if package in _MCP_UNMOUNTABLE:
        return False
    return True


def mountable_peers() -> List[str]:
    """Return the ordered list of packages the umbrella MCP should mount."""
    return [pkg for pkg in ECOSYSTEM if is_mcp_mountable(pkg)]


def should_skip_audit(package: str, auditor: str) -> tuple[bool, str]:
    """Return ``(skip, reason)`` for running ``auditor`` on ``package``.

    ``auditor`` is one of the keys in ``_CATEGORY_SKIP``. Unknown
    auditors return ``(False, "")`` — fail open so a typo doesn't
    silently skip.

    Skip semantics:

    - archived packages are skipped for *every* auditor.
    - per-auditor categories listed in ``_CATEGORY_SKIP`` are skipped.
    - unknown package (not in ECOSYSTEM) is NOT skipped — the
      auditor's own not-found path will handle it.
    """
    info = ECOSYSTEM.get(package)
    if info is None:
        return False, ""
    if info.get("archived"):
        return True, "archived"
    cat = info.get("category", "")
    skip_set = _CATEGORY_SKIP.get(auditor, frozenset())
    if cat in skip_set:
        return True, f"category={cat}"
    return False, ""


# EOF
