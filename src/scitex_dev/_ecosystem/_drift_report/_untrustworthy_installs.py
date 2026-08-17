#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-07-12
# File: scitex_dev/_ecosystem/_drift_report/_untrustworthy_installs.py

"""Installs whose VERSION STRING CANNOT BE BELIEVED — the prior question.

A sibling of, and deliberately separate from, ``_package_watch`` (the
critical-package DRIFT check). "You are behind" and "I cannot tell what
you are running" are different findings with different fixes, and the
second one INVALIDATES the first: a version comparison against a
fossilised ``.dist-info`` is not a weak signal but a WRONG one, in
either direction (false "stale", false "ok"). Collapsing the two would
hide the worse one.

Incident 2026-07-12: a ``.dist-info`` can OUTLIVE the code it describes.
An orphaned ``scitex_todo-0.7.26.dist-info`` sat beside code that was
actually 0.8.7 — thirty releases apart, permanently, with nothing
reporting it. Related sightings: a baked dist-info fossil over current
bound code in scitex-agent-container, and (2026-07-10) an editable
install that deleted the package and left the metadata behind, so every
version check passed against code that was not there.

This module runs BEFORE any version comparison and answers the prior
question honestly: for the same short, hand-picked ``CRITICAL_PACKAGES``
list that ``_package_watch`` compares, which installs are LYING about
what they contain? It refuses to guess, and says so loudly — see
``_release._install_probe`` for the verify-by-CONTENT probe this check
reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..._release._install_probe import (
    KIND_ORPHANED,
    probe_install,
)
from .._core import ECOSYSTEM
from ._model import CRITICAL_PACKAGES


@dataclass(frozen=True)
class UntrustworthyInstallWarning:
    """A package whose VERSION STRING CANNOT BE BELIEVED in this interpreter.

    A DISTINCT warning from :class:`._package_watch.PackageDriftWarning`, and
    deliberately not folded into it: "you are behind" and "I cannot tell what
    you are running" are different problems with different fixes, and collapsing
    them would hide the worse one.

    A ``.dist-info`` can outlive the code it describes (incident 2026-07-12: an
    orphaned ``scitex_todo-0.7.26.dist-info`` sat beside code that was actually
    0.8.7 — thirty releases apart, permanently, with nothing reporting it). When
    that happens, EVERY version-based comparison in ``_package_watch`` is
    meaningless for that package: it will cry "stale" at a current install, or
    bless a stale one. The honest answer is to say so, loudly, and refuse to
    guess.
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


def default_scan_packages() -> tuple[str, ...]:
    """Every registered ecosystem package — the honest default scope.

    Was ``CRITICAL_PACKAGES``: three hand-picked names against a registry of
    seventy. That is not a curation decision, it is a coverage gap wearing
    one, and it DECAYS SILENTLY — one of the three was scitex-todo, which is
    being retired, taking the default scope to two with no code change and no
    notification.

    Widening is safe precisely because of the contract below: a package that
    is not installed is never reported (absence is not a lie), so scanning
    seventy names yields findings only for the installs that actually exist
    in this interpreter and are actually lying.
    """
    return tuple(ECOSYSTEM.keys())


def check_untrustworthy_installs(
    packages: tuple[str, ...] | None = None,
    *,
    probe_fn: Callable[[str], object] = probe_install,
) -> list[UntrustworthyInstallWarning]:
    """Which installed packages have a version string we CANNOT BELIEVE?

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

    ``packages=None`` means EVERY registered package, not a hand-picked few —
    see :func:`default_scan_packages` for why the old three-name default was a
    coverage gap rather than a curation decision. Pass an explicit tuple only
    to narrow deliberately.
    """
    if packages is None:
        packages = default_scan_packages()
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
    # NAME THE INTERPRETER. "this interpreter" is unrecoverable to a reader: a
    # verdict about /opt/venv-sac tells them nothing if they believe it
    # describes their checkout's venv, and nothing on screen distinguishes the
    # two. Measured 2026-08-16 — reporting a venv by its BASENAME cost two
    # agents a round trip when `sac-imgbuild-venv` existed at two paths and we
    # were each looking at a different one.
    #
    # Same principle as the auditors' `N file(s) inspected under <root>` (#654):
    # the scope clause must name the fact the reader cannot otherwise recover,
    # and for a version verdict that fact is WHICH PYTHON was asked.
    import sys as _sys

    bar = "!" * 78
    lines = [
        bar,
        "UNTRUSTWORTHY INSTALL: the version string for these package(s) CANNOT",
        f"BE BELIEVED in {_sys.executable}. Every version-based check below is",
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


# EOF
