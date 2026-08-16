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
from ._package_watch import check_critical_package_drift
from ._sac import collect_sac_rows
from ._untrustworthy_installs import check_untrustworthy_installs


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

    Also runs :func:`_package_watch.check_critical_package_drift` — an
    independent, always-on check of THIS interpreter's critical-package
    installs (never silently skipped when a package's local git checkout
    is absent, unlike layer 8; see that module's docstring for why it
    exists alongside the 8-layer matrix).
    """
    from ..._core.config import load_config
    from ..._release.versions import (
        _normalize_version,
        get_local_path,
        list_versions,
    )
    from .._core import ECOSYSTEM, get_all_packages
    from .._packages import packages_audit
    from ._refs import (
        DEVELOP_REFS,
        MAIN_REFS,
        latest_tag_at_ref,
        newest_tag_in_clone,
        unreachable_tag_note,
        version_at_ref,
    )

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

    installed_versions = {p: _local(p, "installed") for p in pkg_list}
    pypi_versions = {
        p: (lv.get(p, {}).get("remote", {}) or {}).get("pypi") for p in pkg_list
    }

    # THE TWO REFERENCE COLUMNS READ THE REFS THEIR LABELS NAME.
    #
    # Both used to name a remote authority and compute a local artifact, and
    # both were wrong in the same direction on the 2026-08-16 fleet baseline:
    # the SSoT column read the WORKING TREE (any branch, uncommitted edits
    # included -- 15 of 84 surveyed checkouts were off their default branch
    # and 24 were dirty), and the github column ran `git describe` on local
    # HEAD. Neither ever touched the ref it advertised. They are the columns
    # every other column is compared AGAINST, so the error propagated to
    # every verdict in the row.
    #
    # `_refs` REFUSES rather than falling back to something closer to hand: a
    # missing ref yields None, which this report already renders honestly as
    # NOT JUDGEABLE ("a comparison that did not happen"). A silent
    # substitution would render as a verdict instead, which is the defect.
    paths = {p: get_local_path(p) for p in pkg_list}
    ref_readings = {p: version_at_ref(paths[p], DEVELOP_REFS) for p in pkg_list}
    reference_versions = {p: ref_readings[p].value for p in pkg_list}

    tag_readings = {p: latest_tag_at_ref(paths[p], MAIN_REFS) for p in pkg_list}
    tag_versions = {
        p: _normalize_version(tag_readings[p].value) for p in pkg_list
    }
    # "Nothing newer was released" and "something newer was released on a ref
    # this one cannot reach" are different facts that used to render as the
    # same number.
    tag_notes = {
        p: unreachable_tag_note(tag_readings[p], newest_tag_in_clone(paths[p]))
        for p in pkg_list
    }
    tag_notes = {p: note for p, note in tag_notes.items() if note}
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

    # Can we even BELIEVE the version strings for the critical packages? Runs
    # BEFORE the drift comparison, because a comparison against a fossilised
    # .dist-info is not a weak signal but a WRONG one — it cries "stale" at a
    # current install and blesses a stale one (incident 2026-07-12).
    untrustworthy_installs = check_untrustworthy_installs()

    # Critical-package check — always-on, independent of local checkouts.
    package_drift_warnings = check_critical_package_drift()

    return build_drift_matrix(
        packages=pkg_list,
        hosts=host_names,
        reference_versions=reference_versions,
        installed_versions=installed_versions,
        pypi_versions=pypi_versions,
        tag_versions=tag_versions,
        tag_notes=tag_notes,
        sha_rows=sha_rows,
        pypi_names=pypi_names,
        sac_rows=sac_rows,
        sac_note=sac_note,
        package_drift_warnings=tuple(package_drift_warnings),
        untrustworthy_installs=tuple(untrustworthy_installs),
    )


# EOF
