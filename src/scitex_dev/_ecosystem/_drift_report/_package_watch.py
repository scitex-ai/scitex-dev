#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-07-12
# File: scitex_dev/_ecosystem/_drift_report/_package_watch.py

"""Critical shared-infra package staleness — the per-CONTAINER blind spot.

Incident 2026-07-12: an agent container's installed ``scitex-todo`` was
pinned at 0.7.28 while the fleet had moved on to 0.7.50+ (develop: 0.8.4+).
Nothing warned the agent, and it went on to misdiagnose an intentional
schema value as corruption and "fix" (corrupt) ~42 rows of the shared
task store.

Why layer 8 ("editable") did not — and structurally COULD not — catch
this: :func:`._build._classify_version` treats a missing SSoT reference
as *unknown, never drift* (``reference is None -> (False, "no SSoT
reference")``). The SSoT for layer 8 is ``pyproject.toml`` on a LOCAL
GIT CHECKOUT of the package (``_release.versions.get_local_path``). A
lean agent container that only ``pip install``s its dependencies (the
common case — it has no git checkout of every sibling package it
depends on) therefore has ``reference is None`` for every package but
its own repo, and the comparison silently no-ops. The bug is not "no
data" — it is "no data is being SILENTLY treated as no drift" for
exactly the packages a container most needs watched.

This module is a second, independent check that never depends on a
local checkout: for a small critical-package list it compares
``importlib.metadata.version(pkg)`` in the interpreter running
``scitex-dev`` right now against a "fleet-current" reference resolved
with a graceful fallback chain (local checkout's pyproject.toml when
available — the true SSoT — else PyPI latest, the same reference layer
1 already trusts). A package behind that reference is never silent: it
renders a banner distinct from the per-layer matrix so it cannot be
missed by only skimming the table.

This complements, and does not replace, the 8-layer matrix: the matrix
still shows the WIDE cross-host/cross-image picture; this check answers
one narrow, LOUD question for THIS process: "is my own install of a
package the fleet depends on for safety-critical shared state (the task
store) behind?"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..._release._install_probe import (
    KIND_ORPHANED,
    get_version_installed_verified,
    probe_install,
)
from ..._release.versions import (
    _compare_versions,
    _pep440_equal,
    get_pypi_version,
    get_version_from_toml,
)
from .._core import ECOSYSTEM, get_local_path

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


@dataclass(frozen=True)
class UntrustworthyInstallWarning:
    """A package whose VERSION STRING CANNOT BE BELIEVED in this interpreter.

    A DISTINCT warning from :class:`PackageDriftWarning`, and deliberately not
    folded into it: "you are behind" and "I cannot tell what you are running"
    are different problems with different fixes, and collapsing them would hide
    the worse one.

    A ``.dist-info`` can outlive the code it describes (incident 2026-07-12: an
    orphaned ``scitex_todo-0.7.26.dist-info`` sat beside code that was actually
    0.8.7 — thirty releases apart, permanently, with nothing reporting it). When
    that happens, EVERY version-based comparison in this module is meaningless
    for that package: it will cry "stale" at a current install, or bless a stale
    one. The honest answer is to say so, loudly, and refuse to guess.
    """

    package: str
    kind: str  # orphaned | editable(drifted) | unmanaged | ...
    claimed: str | None  # what the .dist-info says
    actual: str | None  # what the code says, when knowable
    detail: str
    hint: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "package": self.package,
            "kind": self.kind,
            "claimed": self.claimed,
            "actual": self.actual,
            "detail": self.detail,
            "hint": self.hint,
        }

    def line(self) -> str:
        if self.kind == KIND_ORPHANED:
            return (
                f"  {self.package}: metadata claims {self.claimed} but NO CODE is "
                f"importable — every version check for it is passing against nothing"
            )
        return (
            f"  {self.package}: metadata claims {self.claimed}, code is actually "
            f"{self.actual or 'UNKNOWN'} — the version string is a fossil"
        )


@dataclass(frozen=True)
class PackageDriftWarning:
    """One critical package found behind its fleet-current reference."""

    package: str
    installed: str
    reference: str
    reference_source: str  # "local-checkout" | "pypi"

    def to_dict(self) -> dict[str, str]:
        return {
            "package": self.package,
            "installed": self.installed,
            "reference": self.reference,
            "reference_source": self.reference_source,
        }

    def line(self) -> str:
        return (
            f"  {self.package}: installed={self.installed}  "
            f"fleet-current={self.reference}  (reference={self.reference_source})"
        )


def _fleet_reference(
    pkg: str,
    *,
    pypi_name: str,
    pypi_fn: Callable[[str], str | None],
    local_path_fn: Callable[[str], object | None],
    toml_fn: Callable[[object], str | None],
) -> tuple[str | None, str]:
    """Resolve the best available fleet-current reference for ``pkg``.

    Prefers the local develop checkout's ``pyproject.toml`` (the true
    SSoT, same as layer 8) when this host happens to have one; falls
    back to PyPI latest so the check still fires from a lean container
    that never git-cloned the package it merely depends on. Returns
    ``(None, "unavailable")`` when neither source resolves — an unknown
    reference is never reported as drift (same "unknown != drift" rule
    as the 8-layer matrix; skill §1).
    """
    local_path = local_path_fn(pkg)
    if local_path is not None and local_path.exists():
        toml_version = toml_fn(local_path)
        if toml_version:
            return toml_version, "local-checkout"
    pypi_version = pypi_fn(pypi_name)
    if pypi_version:
        return pypi_version, "pypi"
    return None, "unavailable"


def check_untrustworthy_installs(
    packages: tuple[str, ...] = CRITICAL_PACKAGES,
    *,
    probe_fn: Callable[[str], object] = probe_install,
) -> list[UntrustworthyInstallWarning]:
    """Which critical packages have a version string we CANNOT BELIEVE?

    Runs BEFORE any version comparison, because a comparison against a fossilised
    ``.dist-info`` is not a weak signal — it is a WRONG one, in either direction:

    * FALSE ALARM: screams "stale, deploy now!" at a container running current
      code, forever, until its reader learns to ignore the whole report.
    * FALSE ALL-CLEAR: blesses a container whose metadata happens to look right
      while the code behind it is stale, missing, or from an abandoned worktree.

    Packages that are simply not installed here are NOT reported — absence is not
    a lie, and this check exists to catch lies. (See ``_install_probe.KIND_ABSENT``:
    reporting an absent package as an orphaned .dist-info would send the reader
    hunting for a directory that does not exist — a confidently wrong hint, which
    is the very disease being treated.)
    """
    out: list[UntrustworthyInstallWarning] = []
    for pkg in packages:
        pypi_name = (ECOSYSTEM.get(pkg, {}) or {}).get("pypi_name", pkg)
        probe = probe_fn(pypi_name)
        # Not installed at all -> nothing is being claimed -> nothing can lie.
        if probe.kind == "absent" or probe.trustworthy:
            continue
        # A bare sys.path entry claims no version; honest by omission.
        if probe.metadata_version is None:
            continue
        out.append(
            UntrustworthyInstallWarning(
                package=pkg,
                kind=probe.kind,
                claimed=probe.metadata_version,
                actual=probe.code_version,
                detail=probe.detail,
                hint=probe.hint,
            )
        )
    return out


def check_critical_package_drift(
    packages: tuple[str, ...] = CRITICAL_PACKAGES,
    *,
    installed_fn: Callable[[str], str | None] = get_version_installed_verified,
    pypi_fn: Callable[[str], str | None] = get_pypi_version,
    local_path_fn: Callable[[str], object | None] = get_local_path,
    toml_fn: Callable[[object], str | None] = get_version_from_toml,
) -> list[PackageDriftWarning]:
    """Compare what THIS interpreter is ACTUALLY RUNNING vs fleet-current.

    ``installed_fn`` defaults to :func:`get_version_installed_verified`, NOT to
    ``importlib.metadata.version``. That difference is the point (incident
    2026-07-12): the metadata string can be a FOSSIL that outlived its code, and
    comparing against a fossil produces a confident wrong answer in both
    directions. The verified reader returns the version of the code that will
    actually execute — the wheel's metadata for a wheel install, the SOURCE's
    declared version for an editable/bound one — and ``None`` when it cannot
    establish that at all.

    ``None`` is treated as UNKNOWN and reported as nothing, never as agreement.
    A package whose install is untrustworthy is not silently mis-compared here;
    it is surfaced by :func:`check_untrustworthy_installs`, which is a louder and
    more urgent finding than being behind.

    Returns one :class:`PackageDriftWarning` per package strictly behind
    its reference. Packages that are not installed here, current, ahead,
    or whose reference cannot be resolved at all are omitted — silence
    on unknown data, never a false "drift" claim.

    ``installed_fn`` / ``pypi_fn`` / ``local_path_fn`` / ``toml_fn`` are
    injectable seams: tests supply fakes so the check needs neither a
    real interpreter install, network access, nor this MACHINE's
    particular set of mounted local checkouts (per the 2026-07-12
    incident fix, this must be unit-testable without any of that — a
    real risk here specifically, since scitex-dev's own dev container
    happens to have every sibling repo checked out under ``~/proj``,
    which would otherwise silently make every test exercise the
    "local-checkout" branch instead of the "lean container" branch it
    is meant to cover).
    """
    warnings: list[PackageDriftWarning] = []
    for pkg in packages:
        pypi_name = (ECOSYSTEM.get(pkg, {}) or {}).get("pypi_name", pkg)
        installed = installed_fn(pypi_name)
        if installed is None:
            continue
        reference, source = _fleet_reference(
            pkg,
            pypi_name=pypi_name,
            pypi_fn=pypi_fn,
            local_path_fn=local_path_fn,
            toml_fn=toml_fn,
        )
        if reference is None:
            continue
        if _pep440_equal(installed, reference):
            continue
        if _compare_versions(installed, reference) < 0:
            warnings.append(
                PackageDriftWarning(
                    package=pkg,
                    installed=installed,
                    reference=reference,
                    reference_source=source,
                )
            )
    return warnings


def render_untrustworthy_install_banner(
    warnings: list[UntrustworthyInstallWarning],
) -> str:
    """LOUDER than the drift banner, because it is a worse finding.

    "You are behind" is a fact you can act on. "I cannot tell what you are
    running" means every other line of this report is unreliable for that
    package — including a reassuring one. Empty string when there is nothing to
    report.
    """
    if not warnings:
        return ""
    bar = "!" * 78
    lines = [
        bar,
        "UNTRUSTWORTHY INSTALL: the version string for these package(s) CANNOT",
        "BE BELIEVED in this interpreter. Every version-based check below is",
        "meaningless for them — in EITHER direction (false 'stale', false 'ok').",
        "",
    ]
    lines.extend(w.line() for w in warnings)
    lines.append("")
    for w in warnings:
        if w.hint:
            lines.append(f"  fix ({w.package}):")
            lines.extend(f"    {ln}" for ln in w.hint.splitlines())
    lines.append("")
    lines.append(
        "A .dist-info can OUTLIVE the code it describes. Verify by CONTENT, never "
        "by the version string alone — see _release._install_probe."
    )
    lines.append(bar)
    return "\n".join(lines)


def render_package_drift_banner(warnings: list[PackageDriftWarning]) -> str:
    """LOUD, hard-to-miss banner — distinct from the per-layer matrix.

    Empty string when there is nothing to report (never prints a banner
    with no content).
    """
    if not warnings:
        return ""
    bar = "!" * 78
    lines = [
        bar,
        "PACKAGE-DRIFT WARNING: critical scitex-* package(s) behind fleet-current",
        "in THIS install (the container/venv that just ran drift-report):",
        "",
    ]
    lines.extend(w.line() for w in warnings)
    lines.append("")
    lines.append(
        "Fix: pip install -U <package>  (or this container's package-upgrade path)."
    )
    lines.append(
        "See _ecosystem._drift_report._package_watch — added after the 2026-07-12 "
        "scitex-todo 0.7.28 incident where a stale container install silently "
        "misdiagnosed valid data as corruption."
    )
    lines.append(bar)
    return "\n".join(lines)


# EOF
