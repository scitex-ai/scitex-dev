#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dist-info-count install-integrity check for the ecosystem version report.

A VERSION STRING IS NOT EVIDENCE THE FIX RUNS. When one site-packages holds
TWO ``*.dist-info`` directories for a single distribution (e.g.
``scitex_cards-0.17.0.dist-info`` AND ``scitex_cards-0.17.7.dist-info``
coexisting), ``importlib.metadata.version()`` reports the NEWER while the
OLDER dist-info's uniquely-owned RECORD files can still win on disk — so
stale code runs while every version check says "current". This has bitten
the fleet repeatedly.

This module is the package-agnostic guard: count the ``*.dist-info``
directories claiming a distribution and treat any count other than 1 as a
distinct condition:

* ``count == 1`` — clean install, no finding.
* ``count == 0`` — not installed here (separate condition; NOT the double
  error — do not conflate).
* ``count  > 1`` — DIRTY INSTALL / half-upgrade. This is an ERROR, reported
  distinctly from an ordinary version mismatch, and its remedy is the
  non-obvious one below.

The non-obvious repair is encoded in :data:`DOUBLE_INSTALL_REMEDY`:
``pip install --force-reinstall`` does NOT fix a double install (pip only
removes the files in the RECORD of the version it is replacing, leaving the
other dist-info's uniquely-owned files behind), so the only reliable fix is
to ``pip uninstall`` REPEATEDLY until the count is 0, then install once.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DIST_INFO_SUFFIX = ".dist-info"

#: The non-obvious repair for a double install — force-reinstall does NOT fix
#: it. Formatted with the distribution name at the point of use.
DOUBLE_INSTALL_REMEDY = (
    "`pip install --force-reinstall` does NOT fix this (pip only removes "
    "files in the RECORD it replaces); run `pip uninstall {dist}` REPEATEDLY "
    "until the dist-info count is 0, then install once, then re-check."
)

#: Truth-in-labeling note for any report that prints a version-derived claim.
DIST_INFO_NOTE = (
    "Versions come from importlib.metadata — a dist-info CLAIM, not proof of "
    "the code that will actually run. Per-package 'dist_info_count' guards "
    "this: a count != 1 means the reported version cannot be trusted (a "
    "double install lets a stale dist-info shadow the newer one)."
)


def _normalize(distribution: str) -> str:
    """Escape a project name to its dist-info stem form.

    Runs of ``-_.`` collapse to a single ``_`` and the result is lowercased,
    so ``scitex-cards`` and ``scitex_cards`` both map to ``scitex_cards``
    (matching the ``scitex_cards-*.dist-info`` naming pip writes).
    """
    return re.sub(r"[-_.]+", "_", str(distribution)).strip("_").lower()


def _interpreter_site_packages() -> list[Path]:
    """Site-packages dirs of the interpreter running this check (deduped)."""
    candidates: list[str] = []
    try:
        import sysconfig

        paths = sysconfig.get_paths()
        for key in ("purelib", "platlib"):
            value = paths.get(key)
            if value:
                candidates.append(value)
    except Exception:  # noqa: BLE001 — best-effort discovery
        pass
    try:
        import site

        if hasattr(site, "getsitepackages"):
            candidates.extend(site.getsitepackages())
        user = site.getusersitepackages()
        if user:
            candidates.append(user)
    except Exception:  # noqa: BLE001 — best-effort discovery
        pass
    out: list[Path] = []
    seen: set[Path] = set()
    for entry in candidates:
        try:
            resolved = Path(entry).resolve()
        except (OSError, ValueError):
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def count_dist_infos(
    distribution: str, site_packages: str | Path | None = None
) -> int:
    """Count ``*.dist-info`` directories claiming ``distribution``.

    Parameters
    ----------
    distribution:
        A project name in any spelling (``scitex-cards`` / ``scitex_cards``);
        normalized PEP 503-style (runs of ``-_.`` → ``_``, lowercased) before
        matching, so it lines up with the ``scitex_cards-*.dist-info`` names
        pip writes on disk.
    site_packages:
        A single directory to search — the NO-MOCK test seam: point it at a
        real tmp dir seeded with ``.dist-info`` directories. When ``None``
        (production), every site-packages dir of the interpreter running the
        check is searched and the counts summed.

    Returns
    -------
    int
        Number of matching ``*.dist-info`` directories (0 = not installed
        here; 1 = clean; > 1 = dirty / half-upgraded install).
    """
    norm = _normalize(distribution)
    if not norm:
        return 0
    if site_packages is None:
        dirs = _interpreter_site_packages()
    else:
        dirs = [Path(site_packages)]

    count = 0
    seen: set[Path] = set()
    for directory in dirs:
        try:
            resolved = Path(directory).resolve()
        except (OSError, ValueError):
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        try:
            children = list(resolved.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.name.endswith(_DIST_INFO_SUFFIX):
                continue
            if not child.is_dir():
                continue
            stem = child.name[: -len(_DIST_INFO_SUFFIX)]
            name_part = stem.rsplit("-", 1)[0] if "-" in stem else stem
            if _normalize(name_part) == norm:
                count += 1
    return count


def dist_info_integrity(
    distribution: str, site_packages: str | Path | None = None
) -> dict[str, Any]:
    """Classify a distribution's dist-info count.

    Returns a dict ``{"count": int, "status": str, "message": str | None}``
    where ``status`` is one of ``"ok"`` (exactly 1), ``"not_installed"``
    (0 — a separate condition, never conflated with the double error), or
    ``"dirty_install"`` (> 1 — the ERROR, with the non-obvious repair in
    ``message``).
    """
    count = count_dist_infos(distribution, site_packages)
    if count > 1:
        message = (
            f"{distribution}: DIRTY INSTALL — {count} *.dist-info directories "
            f"claim this distribution (expected exactly 1). "
            f"importlib.metadata reports the NEWER version while the OLDER "
            f"dist-info's uniquely-owned RECORD files can still win on disk, "
            f"so stale code runs while every version check says 'current'. "
            f"FIX: " + DOUBLE_INSTALL_REMEDY.format(dist=distribution)
        )
        return {"count": count, "status": "dirty_install", "message": message}
    if count == 0:
        return {"count": count, "status": "not_installed", "message": None}
    return {"count": count, "status": "ok", "message": None}


def annotate_dist_info_integrity(local: dict[str, Any], distribution: str) -> None:
    """Record the dist-info count (and any dirty-install message) on ``local``.

    Mutates the ``local`` sub-dict of a version-report entry in place: always
    sets ``dist_info_count``; sets ``dist_info_integrity`` to the repair
    message only when the install is dirty (count > 1).
    """
    result = dist_info_integrity(distribution)
    local["dist_info_count"] = result["count"]
    if result["message"] is not None:
        local["dist_info_integrity"] = result["message"]


def dist_info_status(local: dict[str, Any]) -> tuple[str, list[str]] | None:
    """A ``(status, issues)`` verdict for a dirty install, else ``None``.

    Reads the ``dist_info_count`` previously recorded by
    :func:`annotate_dist_info_integrity`. A dirty install (count > 1) is the
    dominant finding — it invalidates every version-derived comparison — so
    callers return this verdict BEFORE any ordinary mismatch check. count 0
    and 1 yield ``None`` (defer to the normal status logic).
    """
    count = local.get("dist_info_count")
    if isinstance(count, int) and count > 1:
        message = local.get("dist_info_integrity") or (
            f"dirty install — {count} *.dist-info directories claim this "
            f"distribution (expected exactly 1)."
        )
        return "dirty_install", [message]
    return None


# EOF
