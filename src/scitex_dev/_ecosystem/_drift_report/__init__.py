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
    DriftMatrix,
    LayerCell,
    PackageDrift,
    SacFold,
)
from ._sac import collect_sac_rows, fold_sac_versions, parse_sac_output

__all__ = [
    "DriftMatrix",
    "LayerCell",
    "PackageDrift",
    "SacFold",
    "build_drift_matrix",
    "collect_drift_matrix",
    "collect_sac_rows",
    "fold_sac_versions",
    "parse_sac_output",
    "render_matrix",
    "render_quiet",
    "render_report",
]


# EOF
