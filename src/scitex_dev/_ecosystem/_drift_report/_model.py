#!/usr/bin/env python3
# Timestamp: 2026-07-06
# File: scitex_dev/_ecosystem/_drift_report/_model.py

"""Value objects + constants for the version-drift matrix.

Pure data — no I/O. See the package ``__init__`` docstring for the
eight-layer model and the SSoT drift rule.

Also the shared home for ``CRITICAL_PACKAGES``: the two critical-package
checks that hang off the matrix — ``_package_watch`` (are you behind?)
and ``_untrustworthy_installs`` (can your version string be believed?) —
both scope themselves to that one list, and neither owns it. It lives
here, beside the ``DriftMatrix`` fields that carry both checks' results,
so neither check has to import the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._package_watch import PackageDriftWarning
    from ._untrustworthy_installs import UntrustworthyInstallWarning

# --------------------------------------------------------------------- #
# Critical-package watch list (independent of the 8 layers)             #
# --------------------------------------------------------------------- #

#: Packages whose staleness in a single container has already caused
#: real damage (scitex-todo, 2026-07-12) or backs fleet-wide control
#: infrastructure (scitex-agent-container, scitex-dev itself). Extend
#: this tuple as new shared-infra packages earn "every agent depends on
#: this being current" status — it is intentionally a short, hand-picked
#: list, not the full ~90-package ECOSYSTEM registry (that breadth is
#: already the 8-layer matrix's job).
CRITICAL_PACKAGES: tuple[str, ...] = (
    "scitex-todo",
    "scitex-agent-container",
    "scitex-dev",
)

# --------------------------------------------------------------------- #
# Layer identifiers (matrix columns)                                    #
# --------------------------------------------------------------------- #

LAYER_PYPI = "pypi"
LAYER_GITHUB = "github"
LAYER_BASE_IMAGE = "base-image"
LAYER_AGENT_OVERLAY = "agent-overlay"
LAYER_CI = "ci"
LAYER_EDITABLE = "editable"

#: Prefix for per-host checkout-sha columns (``host:spartan`` …).
HOST_LAYER_PREFIX = "host:"

#: Cell "kinds" — how a cell value is read / compared.
KIND_VERSION = "version"  # PEP 440 version string, compared to the SSoT
KIND_SHA = "sha"  # git commit sha, compared to origin/develop
KIND_NA = "na"  # unknown / not-collected — never drift


# --------------------------------------------------------------------- #
# Cells / rows / matrix                                                 #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class LayerCell:
    """One (package, layer) cell.

    ``drift`` is ``True`` iff the cell KNOWINGLY disagrees with its
    reference (the SSoT version for version cells, origin/develop for
    sha cells). An unknown cell (``value is None``) is never drift.
    """

    layer: str
    value: str | None
    kind: str
    drift: bool
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "value": self.value,
            "kind": self.kind,
            "drift": self.drift,
            "note": self.note,
        }


@dataclass(frozen=True)
class PackageDrift:
    """Per-package matrix row."""

    pkg: str
    reference_version: str | None  # pyproject @ develop — the SSoT
    reference_sha: str | None  # origin/develop sha — SSoT for checkouts
    cells: tuple[LayerCell, ...] = ()

    @property
    def drifting_layers(self) -> list[str]:
        return [c.layer for c in self.cells if c.drift]

    @property
    def is_judgeable(self) -> bool:
        """Whether there is a BASELINE to compare the layers against.

        ``reference_version`` is the SSoT (pyproject @ develop). When it is
        None — a setuptools-scm package with no static version, an
        unreadable checkout — every cell has nothing to disagree WITH, so
        no cell is marked drift, so the row looks clean.

        Measured 2026-08-15 on scitex-dev itself, while this report was
        being used to gate a release: ``SSoT=???``, four of seven layers
        blind, pypi 0.49.3 against github 0.49.1, and the summary read
        "1/1 packages consistent; 0 drifting", exit 0.
        """
        return self.reference_version is not None

    @property
    def consistent(self) -> bool:
        """True only when a baseline EXISTS and nothing disagrees with it.

        Without the first half this is TRUE BY VACUITY, which is the same
        defect as a gate reporting a clean result having inspected zero
        lines (scitex-ai/scitex-dev#620). The module already draws this
        distinction for untrustworthy installs -- "I cannot tell what you
        are running" INVALIDATES the comparison rather than passing it --
        and this is that rule applied to the reference value itself.
        """
        return self.is_judgeable and not self.drifting_layers

    def cell(self, layer: str) -> LayerCell | None:
        for c in self.cells:
            if c.layer == layer:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "pkg": self.pkg,
            "reference_version": self.reference_version,
            "reference_sha": self.reference_sha,
            "consistent": self.consistent,
            "drifting_layers": self.drifting_layers,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass(frozen=True)
class DriftMatrix:
    """The whole package × layer matrix plus roll-up state."""

    packages: tuple[PackageDrift, ...] = ()
    layers: tuple[str, ...] = ()
    hosts: tuple[str, ...] = ()
    sac_available: bool = False
    sac_note: str = ""
    #: Critical shared-infra packages (scitex-todo, scitex-agent-container,
    #: scitex-dev, …) found behind fleet-current IN THIS INTERPRETER, per
    #: ``_package_watch.check_critical_package_drift`` — added after the
    #: 2026-07-12 incident where layer 8 ("editable") silently treated a
    #: missing local-checkout reference as "no drift" for a container that
    #: only pip-installs its deps. See ``_package_watch`` module docstring.
    package_drift_warnings: tuple["PackageDriftWarning", ...] = ()
    #: Critical packages whose VERSION STRING CANNOT BE BELIEVED in this
    #: interpreter — an orphaned or drifted ``.dist-info`` that has outlived the
    #: code it describes (incident 2026-07-12: metadata 0.7.26 over code 0.8.7).
    #:
    #: Kept SEPARATE from ``package_drift_warnings`` on purpose: "you are behind"
    #: and "I cannot tell what you are running" are different findings with
    #: different fixes, and the second one INVALIDATES the first for that package
    #: — a version comparison against a fossil is wrong in both directions. See
    #: ``_untrustworthy_installs.check_untrustworthy_installs``.
    untrustworthy_installs: tuple["UntrustworthyInstallWarning", ...] = ()

    @property
    def drifting(self) -> list[PackageDrift]:
        """Packages KNOWN to disagree with their baseline.

        Excludes unjudgeable rows on purpose: "this layer is behind" and
        "there was nothing to compare against" are different findings with
        different fixes, and folding the second into the first would send a
        reader hunting for a version mismatch that was never measured.
        """
        return [p for p in self.packages if p.is_judgeable and not p.consistent]

    @property
    def unjudgeable(self) -> list[PackageDrift]:
        """Packages with NO baseline — neither consistent nor drifting.

        The third value. A count that hides these reports health it never
        established.
        """
        return [p for p in self.packages if not p.is_judgeable]

    @property
    def consistent_packages(self) -> list[PackageDrift]:
        return [p for p in self.packages if p.consistent]

    @property
    def has_drift(self) -> bool:
        # An untrustworthy install counts as a finding: not knowing what you are
        # running is at least as serious as knowing you are behind, and a report
        # that exits clean while a package's version string is a fossil is
        # exactly the false all-clear this check exists to prevent.
        #
        # An UNJUDGEABLE package counts for the same reason, one step
        # earlier: a row with no baseline has not been shown to be in sync,
        # and exiting 0 on it is a clean bill of health from a comparison
        # that never happened.
        return (
            bool(self.drifting)
            or bool(self.unjudgeable)
            or bool(self.package_drift_warnings)
            or bool(self.untrustworthy_installs)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "layers": list(self.layers),
            "hosts": list(self.hosts),
            "sac_available": self.sac_available,
            "sac_note": self.sac_note,
            "summary": {
                "total": len(self.packages),
                "consistent": len(self.consistent_packages),
                "drifting": len(self.drifting),
            },
            "packages": [p.to_dict() for p in self.packages],
            "package_drift_warnings": [w.to_dict() for w in self.package_drift_warnings],
            "untrustworthy_installs": [
                w.to_dict() for w in self.untrustworthy_installs
            ],
        }


# --------------------------------------------------------------------- #
# sac fold — layers 5 (base-image) + 6 (agent-overlay)                  #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class SacFold:
    """Folded view of the flat ``sac versions --json`` rows.

    Effective version for an agent = the agent-overlay row for that
    package if present, ELSE the base-image row for that agent's image.
    """

    base_by_image: dict[str, dict[str, str]] = field(default_factory=dict)
    overlay_by_agent: dict[str, dict[str, str]] = field(default_factory=dict)
    agent_image: dict[str, str] = field(default_factory=dict)

    def effective(self, agent: str, package: str) -> str | None:
        """Overlay-else-base effective version for ``(agent, package)``."""
        overlay = self.overlay_by_agent.get(agent, {})
        if package in overlay:
            return overlay[package]
        image = self.agent_image.get(agent)
        if image is None:
            return None
        return self.base_by_image.get(image, {}).get(package)

    def base_versions_for(self, package: str) -> dict[str, str]:
        """``{image: version}`` for every image carrying ``package``."""
        return {
            image: pkgs[package]
            for image, pkgs in self.base_by_image.items()
            if package in pkgs
        }

    def effective_versions_for(self, package: str) -> dict[str, str]:
        """``{agent: effective_version}`` for every known agent."""
        out: dict[str, str] = {}
        for agent in set(self.overlay_by_agent) | set(self.agent_image):
            v = self.effective(agent, package)
            if v is not None:
                out[agent] = v
        return out


# EOF
