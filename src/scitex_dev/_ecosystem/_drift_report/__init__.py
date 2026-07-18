#!/usr/bin/env python3
# Timestamp: 2026-07-06
# File: scitex_dev/_ecosystem/_drift_report/__init__.py

"""Unified per-package × per-layer version-drift matrix.

Backs ``scitex-dev ecosystem drift-report``. Implements the *observe
pass* of the eight-layer drift matrix defined in
``_skills/general/05_development/13_version-drift-management.md``
(§1 matrix, §2 observe, §5 the north-star report): ONE matrix, package
rows × layer columns → version, so version drift across PyPI / GitHub /
hosts / container-image / agent-overlay / CI / editable installs is
identifiable at a glance.

The eight layers (per package)
------------------------------
1. **PyPI** — published latest version.
2. **GitHub** — latest release tag (what ``main`` shipped) + the
   develop-checkout sha (see the per-host / localhost sha columns).
3. **Host ``ywata-note-win``** — develop-checkout sha (via
   ``packages_audit``).
4. **Host ``spartan``** — develop-checkout sha (degrades to ``-`` when
   unreachable).
5. **Container base image** — via ``sac versions --json`` (layer
   ``base-image``).
6. **Agent overlay** — via ``sac versions --json`` (overlay-else-base
   effective version per agent).
7. **CI** — out of scope for v1; reported honestly as ``not-collected``
   (never faked).
8. **Editable / local checkout** — the current interpreter's installed
   version + the localhost develop sha.

Critical-package check (independent of the 8 layers)
------------------------------------------------------
Layer 8 silently treats "no local git checkout of this package" as
"unknown, not drift" — correct for the matrix's SSoT rule, but it means
a lean container that only ``pip install``s its dependencies (never
clones every sibling repo) gets NO warning when one of them goes stale.
This bit a real agent 2026-07-12 (``scitex-todo`` pinned at 0.7.28 while
the fleet moved to 0.7.50+). ``_package_watch.check_critical_package_drift``
closes that gap for a short, hand-picked critical-package list
(``scitex-todo``, ``scitex-agent-container``, ``scitex-dev`` — see
``CRITICAL_PACKAGES``): it compares THIS interpreter's installed version
against a fleet-current reference that falls back to PyPI latest when no
local checkout exists, and renders a LOUD banner (never silent) ahead of
the matrix in ``render_report`` whenever one is behind.

That comparison presumes the installed version string can be BELIEVED —
a ``.dist-info`` can outlive the code it describes, and comparing against
such a fossil is wrong in BOTH directions (false "stale", false "ok").
``_untrustworthy_installs.check_untrustworthy_installs`` answers that
prior question over the same ``CRITICAL_PACKAGES`` list and renders an
even louder banner, because "I cannot tell what you are running"
invalidates every version-based line of this report for that package.

Architecture — a pure core + a thin collector
----------------------------------------------
Everything network-/subprocess-touching lives in ``_collect`` (and the
``collect_sac_rows`` helper in ``_sac``). The AGGREGATION is pure and
fully unit-testable without a network, SSH, or ``sac`` on PATH:
``build_drift_matrix`` / ``fold_sac_versions`` / ``parse_sac_output`` and
the cell-classification helpers. Tests inject plain data (mirroring
``_packages.py``'s sha-fn seams) — no mocks.

The SSoT rule (skill §1): "what SHOULD the version be?" is the
``pyproject.toml`` version on the local develop checkout; "what IS
published?" is PyPI. Every other layer is a *cache* of the SSoT — a cell
that disagrees is drift. Only a KNOWN-different value is drift; an
*unknown* cell (host unreachable, package not installed, a not-collected
layer, ``sac`` absent) renders ``-`` and never counts as drift, so a
sleeping laptop or a missing ``sac`` verb does not turn the gate
permanently red (skill §4 "broken feedback loop" anti-pattern).
"""

from __future__ import annotations

from ._build import (
    build_drift_matrix,
    render_matrix,
    render_quiet,
    render_report,
)
from ._collect import collect_drift_matrix
from ._model import (
    CRITICAL_PACKAGES,
    DriftMatrix,
    LayerCell,
    PackageDrift,
    SacFold,
)
from ._package_watch import (
    PackageDriftWarning,
    check_critical_package_drift,
    render_package_drift_banner,
)
from ._sac import collect_sac_rows, fold_sac_versions, parse_sac_output
from ._untrustworthy_installs import (
    UntrustworthyInstallWarning,
    check_untrustworthy_installs,
    render_untrustworthy_install_banner,
)

__all__ = [
    "CRITICAL_PACKAGES",
    "DriftMatrix",
    "LayerCell",
    "PackageDrift",
    "PackageDriftWarning",
    "SacFold",
    "UntrustworthyInstallWarning",
    "build_drift_matrix",
    "check_critical_package_drift",
    "check_untrustworthy_installs",
    "collect_drift_matrix",
    "collect_sac_rows",
    "fold_sac_versions",
    "parse_sac_output",
    "render_matrix",
    "render_package_drift_banner",
    "render_untrustworthy_install_banner",
    "render_quiet",
    "render_report",
]


# EOF
