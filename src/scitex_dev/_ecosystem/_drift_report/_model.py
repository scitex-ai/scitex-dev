#!/usr/bin/env python3
# Timestamp: 2026-07-06
# File: scitex_dev/_ecosystem/_drift_report/_model.py

"""Value objects + layer constants for the version-drift matrix.

Pure data — no I/O. See the package ``__init__`` docstring for the
eight-layer model and the SSoT drift rule.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
    def consistent(self) -> bool:
        return not self.drifting_layers

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

    @property
    def drifting(self) -> list[PackageDrift]:
        return [p for p in self.packages if not p.consistent]

    @property
    def consistent_packages(self) -> list[PackageDrift]:
        return [p for p in self.packages if p.consistent]

    @property
    def has_drift(self) -> bool:
        return bool(self.drifting)

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
