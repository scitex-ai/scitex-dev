#!/usr/bin/env python3
# Timestamp: 2026-07-06
# File: scitex_dev/_ecosystem/_drift_report/_collect.py

"""Live collection — the network / subprocess side of the drift report.

Thin orchestrator: it gathers each layer from the EXISTING ecosystem
helpers (no reinvention) and hands plain per-package dicts to the pure
:func:`build_drift_matrix`. Not unit-tested (it does real I/O); the pure
core it feeds is fully covered.
"""

from __future__ import annotations

from typing import Callable

from ._build import build_drift_matrix
from ._model import DriftMatrix
from ._sac import collect_sac_rows


def collect_drift_matrix(
    *,
    packages: list[str] | None = None,
    hosts: list[str] | None = None,
    config=None,
    sac_runner: Callable[[list[str]], tuple[int, str, str]] | None = None,
) -> DriftMatrix:
    """Gather every layer live and assemble the matrix.

    Reuses, rather than reinvents:

    * ``scitex_dev._release.versions.list_versions`` — layers 1 (PyPI),
      2-tag (GitHub release), 8 (installed / editable), and the SSoT
      pyproject version, in one pass.
    * ``scitex_dev._ecosystem._packages.packages_audit`` — the
      develop-checkout sha columns for localhost + each host (layers
      2-develop / 3 / 4 / 8-sha).
    * ``sac versions --json`` — layers 5/6, via :func:`collect_sac_rows`
      (fail-open).
    """
    from ..._core.config import load_config
    from ..._release.versions import _normalize_version, list_versions
    from .._core import ECOSYSTEM, get_all_packages
    from .._packages import packages_audit

    if config is None:
        config = load_config()

    all_pkgs = get_all_packages()
    if packages:
        wanted = set(packages)
        pkg_list = [p for p in all_pkgs if p in wanted]
    else:
        pkg_list = list(all_pkgs)

    # Layers 1 / 2-tag / 8-installed / SSoT — one reused pass.
    lv = list_versions(pkg_list)

    def _local(pkg: str, key: str) -> str | None:
        return (lv.get(pkg, {}).get("local", {}) or {}).get(key)

    reference_versions = {p: _local(p, "pyproject_toml") for p in pkg_list}
    installed_versions = {p: _local(p, "installed") for p in pkg_list}
    pypi_versions = {
        p: (lv.get(p, {}).get("remote", {}) or {}).get("pypi") for p in pkg_list
    }
    tag_versions = {
        p: _normalize_version((lv.get(p, {}).get("git", {}) or {}).get("latest_tag"))
        for p in pkg_list
    }
    pypi_names = {
        p: (ECOSYSTEM.get(p, {}) or {}).get("pypi_name", p) for p in pkg_list
    }

    # Layers 2-develop / 3 / 4 / 8-sha — reuse packages_audit verbatim.
    audit = packages_audit(
        mode="observe",
        hosts=hosts,
        packages=packages,
        config=config,
    )
    state = audit.get("state", {})
    sha_rows = state.get("rows", [])
    host_names = list(state.get("hosts", []))

    # Layers 5 / 6 — sac (fail-open).
    sac_rows, sac_note = collect_sac_rows(runner=sac_runner)

    return build_drift_matrix(
        packages=pkg_list,
        hosts=host_names,
        reference_versions=reference_versions,
        installed_versions=installed_versions,
        pypi_versions=pypi_versions,
        tag_versions=tag_versions,
        sha_rows=sha_rows,
        pypi_names=pypi_names,
        sac_rows=sac_rows,
        sac_note=sac_note,
    )


# EOF
