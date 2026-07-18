#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_checks.py

"""Install-currency DISPATCH + report assembly. The safety of #2 lives here.

The install-currency check is the one that MUST behave differently by install
kind, and getting that wrong is the dangerous bug this whole primitive exists
to prevent:

* WHEEL     — the metadata shipped beside the code, so a version compare
  against PyPI is honest. STALE => ``pip install -U``.
* EDITABLE  — the metadata is a FOSSIL frozen at ``pip install -e``; a
  version compare would fire a FALSE STALE whose remedy CLOBBERS the
  checkout. So we ask the CONTENT (working tree vs its tag) instead, and the
  remedy is a ``git pull``, NEVER ``pip install -U``.
* ORPHANED  — a ``.dist-info`` with NO importable code behind it. STALE.
* ABSENT / UNMANAGED / unknown — UNKNOWN. Absence is not staleness.

The other four checks live in :mod:`._ship_checks`. Every finding is stamped
here with the BINARY that answered — package origin + interpreter — so a
reader can always tell WHOSE verdict this is.
"""

from __future__ import annotations

import time
from dataclasses import replace

from . import _version
from ._model import Currency, Finding, Report
from ._ship_checks import (
    check_ghost_tags,
    check_release_runs,
    check_running_vs_installed,
    check_symbols,
)

__all__ = [
    "build_report",
    "check_ghost_tags",
    "check_install_currency",
    "check_release_runs",
    "check_running_vs_installed",
    "check_symbols",
]


def _unknown(check: str, why: str) -> Finding:
    return Finding(check=check, state=Currency.UNKNOWN, summary=why)


# ---------------------------------------------------------------------------
# install-currency — the dispatch that keeps the dangerous check off editable
# ---------------------------------------------------------------------------


def check_install_currency(
    kind,
    *,
    dist: str,
    effective,
    metadata,
    latest,
    ahead_behind,
    python=None,
) -> Finding:
    """Is the installed/loaded code current? Dispatched on install KIND."""
    check = "install-currency"

    if kind == "wheel":
        return _wheel_currency(check, dist, effective or metadata, latest, python)
    if kind == "editable":
        return _editable_currency(check, dist, ahead_behind, metadata, latest)
    if kind == "orphaned":
        return Finding(
            check=check,
            state=Currency.STALE,
            summary=(
                f"ORPHANED INSTALL: metadata claims {dist} {metadata or '?'} "
                f"but no importable code is behind it"
            ),
            remedy=f"pip install --force-reinstall --no-deps {dist}",
            detail=(
                "A .dist-info outlived the code it describes, so every "
                "version check PASSES against a package that is not there. "
                "This is the dangerous false-all-clear: refresh the install "
                "or delete the stale .dist-info."
            ),
            data={"install_kind": kind, "metadata_version": metadata},
        )
    if kind == "absent":
        return _unknown(check, f"{dist} is not installed — nothing to compare")
    return _unknown(
        check, f"cannot establish install kind for {dist} ({kind!r})"
    )


def _wheel_currency(check, dist, installed, latest, python) -> Finding:
    if not installed:
        return _unknown(check, "installed version unknown (package not installed?)")
    if not latest:
        return _unknown(check, "PyPI unreachable — cannot tell what shipped")
    behind = _version.is_behind(installed, latest)
    if behind is None:
        return _unknown(check, f"cannot order versions {installed!r} vs {latest!r}")
    if not behind:
        return Finding(
            check=check,
            state=Currency.FRESH,
            summary=f"installed {installed} is current with PyPI ({latest})",
            data={"install_kind": "wheel", "installed": installed, "pypi_latest": latest},
        )
    exe = python or "python"
    return Finding(
        check=check,
        state=Currency.STALE,
        summary=f"installed {installed} is BEHIND PyPI {latest}",
        remedy=f"{exe} -m pip install -U '{dist}=={latest}'",
        detail=(
            "The fixes released between these two versions are NOT running "
            "on this machine. Upgrading is not enough on its own — any "
            "long-lived process also has to be restarted, because Python "
            "does not reload modules in a live process."
        ),
        data={"install_kind": "wheel", "installed": installed, "pypi_latest": latest},
    )


def _editable_currency(check, dist, ahead_behind, metadata, latest) -> Finding:
    """The CONTENT probe. The version string is deliberately ignored here.

    ``ahead_behind`` is ``(ahead, behind)`` of the working tree vs its own
    latest release tag, from :func:`_editable.editable_ahead_behind` (which
    reuses ``check_editable_drift``). ``None`` => UNKNOWN.

    The frozen ``metadata`` being behind ``latest`` PyPI is EXPECTED for an
    editable checkout and is emphatically NOT stale — that is the exact false
    positive this branch exists to refuse. So it never appears as a remedy,
    and never as STALE.
    """
    if ahead_behind is None:
        return _unknown(
            check,
            "editable install: no git checkout / release tag to compare "
            "against (the frozen metadata is NOT used — it is a fossil here)",
        )
    ahead, behind = ahead_behind
    data = {
        "install_kind": "editable",
        "ahead": ahead,
        "behind": behind,
        "metadata_version": metadata,
        "pypi_latest": latest,
    }
    if behind == 0:
        # Ahead-only or exactly on the tag: the working tree carries every
        # released commit. FRESH by CONTENT, whatever the fossil metadata or
        # PyPI says. This is the negative-test case.
        return Finding(
            check=check,
            state=Currency.FRESH,
            summary=(
                f"editable checkout is current by content "
                f"(+{ahead}/-0 vs its latest tag); frozen metadata "
                f"{metadata or '?'} is a fossil and is ignored"
            ),
            data=data,
        )
    if ahead:
        return Finding(
            check=check,
            state=Currency.STALE,
            summary=(
                f"editable checkout DIVERGED from its latest tag "
                f"(+{ahead}/-{behind})"
            ),
            remedy="git pull --rebase",
            detail=(
                "The working tree is missing released commits. This is a "
                "CONTENT verdict, not a version-string one — and the fix is a "
                "git pull, never `pip install -U`, which would replace the "
                "editable checkout with a wheel."
            ),
            data=data,
        )
    return Finding(
        check=check,
        state=Currency.STALE,
        summary=f"editable checkout is {behind} commit(s) BEHIND its latest tag",
        remedy="git pull",
        detail=(
            "The working tree is behind the latest release tag. Fix by "
            "pulling — NEVER `pip install -U`, which would clobber the "
            "editable checkout with a wheel."
        ),
        data=data,
    )


# ---------------------------------------------------------------------------
# assembly + name-the-binary stamping
# ---------------------------------------------------------------------------


def _binary_tag(dist: str, origin: str | None, executable: str) -> str:
    """The string that names WHOSE verdict this is.

    ``scitex-dev @ /path/to/__init__.py (python /opt/venv/bin/python3)`` —
    package origin AND interpreter. A message that does not say whose
    "0.21.21 is behind 0.21.24" this is, is useless (sac had FIVE installs).
    """
    return f"{dist} @ {origin or '?'} (python {executable})"


def _stamp(finding: Finding, binary: str, origin: str | None, executable: str) -> Finding:
    """Fold the binary tag into every finding's summary and data.

    The summary contract (name-the-binary) is enforced HERE, once, for every
    check, rather than threaded through each — so no check can forget it.
    """
    summary = f"{finding.summary}  [{binary}]"
    data = {
        **finding.data,
        "binary": binary,
        "origin": origin,
        "executable": executable,
    }
    return replace(finding, summary=summary, data=data)


def build_report(config, sources, *, now=None) -> Report:
    """Run every check against ``sources`` and assemble the stamped report.

    ``config`` is a :class:`~scitex_dev.versioning._config.VersioningConfig`;
    ``sources`` is any :class:`~scitex_dev.versioning._sources.Sources`.
    """
    origin = sources.module_origin()
    executable = sources.executable()
    binary = _binary_tag(config.dist, origin, executable)

    raw_findings = (
        check_install_currency(
            sources.install_kind(),
            dist=config.dist,
            effective=sources.effective_version(),
            metadata=sources.metadata_version(),
            latest=sources.pypi_latest(),
            ahead_behind=sources.editable_ahead_behind(),
            python=executable,
        ),
        check_ghost_tags(sources.git_tags(), sources.pypi_versions()),
        check_running_vs_installed(
            sources.daemon_started_at(),
            sources.installed_at(),
            unit=config.systemd_unit,
        ),
        check_release_runs(sources.release_runs()),
        check_symbols(config.expectations),
    )
    findings = tuple(_stamp(f, binary, origin, executable) for f in raw_findings)
    return Report(
        findings=findings,
        generated_at=time.time() if now is None else now,
    )


# EOF
