#!/usr/bin/env python3
# Timestamp: 2026-07-06
# File: scitex_dev/_ecosystem/_drift_report/_build.py

"""Matrix assembly + drift classification + human rendering.

Everything here is PURE (no network / subprocess / SSH). Version-drift
comparison reuses ``scitex_dev._release.versions`` helpers rather than
re-implementing PEP 440 logic.
"""

from __future__ import annotations

from typing import Any

from ..._release.versions import _compare_versions, _pep440_equal
from ._model import (
    HOST_LAYER_PREFIX,
    KIND_NA,
    KIND_SHA,
    KIND_VERSION,
    LAYER_AGENT_OVERLAY,
    LAYER_BASE_IMAGE,
    LAYER_CI,
    LAYER_EDITABLE,
    LAYER_GITHUB,
    LAYER_PYPI,
    DriftMatrix,
    LayerCell,
    PackageDrift,
    SacFold,
)
from ._sac import fold_sac_versions


# --------------------------------------------------------------------- #
# Cell drift classification                                             #
# --------------------------------------------------------------------- #


def _classify_version(
    value: str | None, reference: str | None
) -> tuple[bool, str]:
    """``(drift, note)`` for a version cell compared to the SSoT.

    Unknown (either side ``None``) is never drift.
    """
    if value is None:
        return False, ""
    if reference is None:
        return False, "no SSoT reference"
    if _pep440_equal(value, reference):
        return False, ""
    cmp = _compare_versions(value, reference)
    if cmp < 0:
        return True, "behind SSoT"
    if cmp > 0:
        return True, "ahead of SSoT"
    return True, "differs from SSoT"


def _sha_drift(value: Any, reference: str | None) -> bool:
    """True iff a KNOWN sha cell differs from origin/develop.

    ``EXCLUDED`` / ``ERROR`` / ``None`` / a missing reference are all
    *unknown* — not drift.
    """
    if not reference:
        return False
    if value in (None, "EXCLUDED", "ERROR"):
        return False
    if not isinstance(value, str):
        return False
    return value != reference


def _short(sha: Any) -> str | None:
    if not isinstance(sha, str) or not sha:
        return None
    return sha[:7]


def _representative_version_cell(
    layer: str, versions: dict[str, str], reference: str | None
) -> LayerCell:
    """Collapse ``{key: version}`` (per image / per agent) into one cell.

    * empty         → unknown (``-``), not drift.
    * one distinct  → that version, drift per SSoT comparison.
    * many distinct → ``"mixed"``, ALWAYS drift (inconsistent across the
      images/agents), with the breakdown in ``note``.
    """
    if not versions:
        return LayerCell(layer=layer, value=None, kind=KIND_NA, drift=False)
    distinct = sorted(set(versions.values()))
    if len(distinct) == 1:
        drift, note = _classify_version(distinct[0], reference)
        return LayerCell(layer, distinct[0], KIND_VERSION, drift, note)
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(versions.items()))
    return LayerCell(layer, "mixed", KIND_VERSION, True, f"mixed: {breakdown}")


def _host_sha_cell(host: str, raw: Any, reference_sha: str | None) -> LayerCell:
    """Build the ``host:<name>`` sha cell from a packages_audit cell."""
    layer = f"{HOST_LAYER_PREFIX}{host}"
    if raw == "EXCLUDED":
        return LayerCell(layer, None, KIND_NA, False, "excluded")
    if raw in (None, "ERROR"):
        return LayerCell(layer, None, KIND_NA, False, "unreachable or not installed")
    drift = _sha_drift(raw, reference_sha)
    return LayerCell(
        layer,
        _short(raw),
        KIND_SHA,
        drift,
        "differs from origin/develop" if drift else "",
    )


def _sac_layer_cell(
    layer: str,
    sac_fold: SacFold | None,
    pypi_name: str,
    reference: str | None,
    *,
    base: bool,
) -> LayerCell:
    """Build the base-image (``base=True``) or agent-overlay cell."""
    if sac_fold is None:
        return LayerCell(layer, None, KIND_NA, False, "sac unavailable")
    versions = (
        sac_fold.base_versions_for(pypi_name)
        if base
        else sac_fold.effective_versions_for(pypi_name)
    )
    return _representative_version_cell(layer, versions, reference)


# --------------------------------------------------------------------- #
# Matrix assembly                                                       #
# --------------------------------------------------------------------- #


def build_drift_matrix(
    *,
    packages: list[str],
    hosts: list[str],
    reference_versions: dict[str, str | None],
    installed_versions: dict[str, str | None],
    pypi_versions: dict[str, str | None],
    tag_versions: dict[str, str | None],
    sha_rows: list[dict],
    pypi_names: dict[str, str],
    sac_rows: list[dict] | None,
    sac_note: str = "",
) -> DriftMatrix:
    """Fold plain per-package inputs into a :class:`DriftMatrix`.

    Pure — every argument is plain data (no network / subprocess), so the
    whole assembly is unit-testable with synthetic fixtures.

    ``sha_rows`` is ``packages_audit(...)["state"]["rows"]`` reused
    verbatim for the develop-checkout sha columns. ``pypi_names`` maps
    each ecosystem key to its pip/PyPI name so ``sac`` rows (which key on
    the PyPI name) match the right package. ``sac_rows is None`` marks
    layers 5/6 unavailable (rendered ``-`` with ``sac_note``).
    """
    sha_by_pkg = {r.get("pkg"): r for r in sha_rows}
    sac_fold = fold_sac_versions(sac_rows) if sac_rows is not None else None
    sac_available = sac_rows is not None

    layers: tuple[str, ...] = (
        LAYER_PYPI,
        LAYER_GITHUB,
        *(f"{HOST_LAYER_PREFIX}{h}" for h in hosts),
        LAYER_BASE_IMAGE,
        LAYER_AGENT_OVERLAY,
        LAYER_CI,
        LAYER_EDITABLE,
    )

    rows: list[PackageDrift] = []
    for pkg in packages:
        reference = reference_versions.get(pkg)
        sha_row = sha_by_pkg.get(pkg, {})
        reference_sha = sha_row.get("origin")
        host_cells = sha_row.get("cells", {}) or {}
        pypi_name = pypi_names.get(pkg, pkg)

        cells: list[LayerCell] = []

        # Layer 1 — PyPI latest.
        drift, note = _classify_version(pypi_versions.get(pkg), reference)
        cells.append(
            LayerCell(LAYER_PYPI, pypi_versions.get(pkg), KIND_VERSION, drift, note)
        )

        # Layer 2 — GitHub: latest release tag (what `main` shipped).
        tag = tag_versions.get(pkg)
        drift, note = _classify_version(tag, reference)
        cells.append(LayerCell(LAYER_GITHUB, tag, KIND_VERSION, drift, note))

        # Layers 3/4 (+ 8-sha) — per-host develop checkout sha vs origin.
        for host in hosts:
            cells.append(_host_sha_cell(host, host_cells.get(host), reference_sha))

        # Layer 5 — container base image (sac).
        cells.append(
            _sac_layer_cell(LAYER_BASE_IMAGE, sac_fold, pypi_name, reference, base=True)
        )

        # Layer 6 — agent overlay effective (sac).
        cells.append(
            _sac_layer_cell(
                LAYER_AGENT_OVERLAY, sac_fold, pypi_name, reference, base=False
            )
        )

        # Layer 7 — CI (out of scope for v1; honestly "not-collected").
        cells.append(LayerCell(LAYER_CI, None, KIND_NA, False, "not-collected (v1)"))

        # Layer 8 — editable / current-interpreter installed version.
        installed = installed_versions.get(pkg)
        drift, note = _classify_version(installed, reference)
        cells.append(LayerCell(LAYER_EDITABLE, installed, KIND_VERSION, drift, note))

        rows.append(
            PackageDrift(
                pkg=pkg,
                reference_version=reference,
                reference_sha=reference_sha,
                cells=tuple(cells),
            )
        )

    return DriftMatrix(
        packages=tuple(rows),
        layers=layers,
        hosts=tuple(hosts),
        sac_available=sac_available,
        sac_note=sac_note,
    )


# --------------------------------------------------------------------- #
# Rendering — human report                                              #
# --------------------------------------------------------------------- #


def _cell_repr(cell: LayerCell) -> str:
    """Fixed-width cell text: value + ``*`` on drift, ``-`` when unknown."""
    if cell.value is None:
        return "-"
    return f"{cell.value}{'*' if cell.drift else ''}"


def _layer_header(layer: str) -> str:
    """Short column header for a layer key."""
    if layer.startswith(HOST_LAYER_PREFIX):
        return layer[len(HOST_LAYER_PREFIX):]
    return {
        LAYER_PYPI: "pypi",
        LAYER_GITHUB: "github",
        LAYER_BASE_IMAGE: "img",
        LAYER_AGENT_OVERLAY: "overlay",
        LAYER_CI: "ci",
        LAYER_EDITABLE: "editable",
    }.get(layer, layer)


def render_matrix(matrix: DriftMatrix) -> str:
    """Render the full package × layer grid (mirrors validate-versions)."""
    headers = ["pkg", "SSoT"] + [_layer_header(la) for la in matrix.layers]
    body: list[list[str]] = []
    for p in matrix.packages:
        line = [p.pkg, p.reference_version or "???"]
        for layer in matrix.layers:
            cell = p.cell(layer)
            line.append(_cell_repr(cell) if cell else "-")
        body.append(line)

    cols = [headers] + body
    widths = [max(len(str(row[i])) for row in cols) for i in range(len(headers))]

    def fmt(row: list[str]) -> str:
        return "  ".join(str(v).ljust(widths[i]) for i, v in enumerate(row))

    out = [fmt(headers), fmt(["-" * w for w in widths])]
    out.extend(fmt(r) for r in body)
    return "\n".join(out)


def render_report(matrix: DriftMatrix) -> str:
    """Full human report: title, grid, summary, per-drift detail."""
    lines: list[str] = [
        "SciTeX ecosystem drift report "
        "(SSoT = pyproject.toml @ local develop; * = drift vs SSoT)",
        "",
        render_matrix(matrix),
        "",
    ]

    total = len(matrix.packages)
    consistent = len(matrix.consistent_packages)
    drifting = matrix.drifting
    lines.append(
        f"summary: {consistent}/{total} packages consistent; "
        f"{len(drifting)} drifting"
    )

    if drifting:
        lines.append("")
        lines.append("drift detail (which layer disagrees, per package):")
        for p in drifting:
            frags = []
            for cell in p.cells:
                if not cell.drift:
                    continue
                tag = f"{cell.layer}={cell.value}"
                if cell.note:
                    tag += f" ({cell.note})"
                frags.append(tag)
            lines.append(
                f"  {p.pkg}  SSoT={p.reference_version or '???'}  | "
                + "  ".join(frags)
            )

    notes = ["ci: not-collected (out of scope for v1)"]
    if not matrix.sac_available:
        notes.append(
            f"base-image/agent-overlay: {matrix.sac_note or 'sac unavailable'}"
        )
    lines.append("")
    lines.append("layers not fully collected: " + "; ".join(notes))
    return "\n".join(lines)


def render_quiet(matrix: DriftMatrix) -> str:
    """One-line summary."""
    total = len(matrix.packages)
    consistent = len(matrix.consistent_packages)
    return (
        f"drift: {consistent}/{total} packages consistent; "
        f"{len(matrix.drifting)} drifting"
        + ("" if matrix.sac_available else " (sac layers 5/6 unavailable)")
    )


# EOF
