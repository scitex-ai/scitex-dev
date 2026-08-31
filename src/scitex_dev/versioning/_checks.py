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
  checkout. So we ask the CONTENT instead — and CONTENT means TWO facts,
  not one. Distance from the latest release tag says only whether that tag
  is in HEAD's history; distance from the TRACKING REMOTE says whether a
  pull can do anything about it. Only the second one can make this STALE,
  because a pull moves HEAD toward ``origin/<branch>`` and nowhere else.
  The remedy is ``git -C <repo> pull --ff-only``, NEVER ``pip install -U``.
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
    behind_upstream=None,
    repo=None,
    python=None,
) -> Finding:
    """Is the installed/loaded code current? Dispatched on install KIND.

    ``behind_upstream`` and ``repo`` are only consulted for an editable
    install: the first decides whether a pull can close the gap, the second
    makes the printed remedy CWD-independent. Both default to ``None``
    (=> "no evidence"), so a caller that cannot supply them gets UNKNOWN
    rather than a verdict built on a fact nobody measured.
    """
    check = "install-currency"

    if kind == "wheel":
        return _wheel_currency(check, dist, effective or metadata, latest, python)
    if kind == "editable":
        return _editable_currency(
            check, dist, ahead_behind, behind_upstream, repo, metadata, latest
        )
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


def _pull_remedy(repo) -> str:
    """The ONLY pull this module may print.

    ``-C <abs repo>`` because the reader's shell is not necessarily in the
    checkout, and a bare ``git pull`` typed from somewhere else operates on
    the wrong repository. ``--ff-only`` because ``--rebase`` REWRITES the
    developer's unpushed commits — a remedy for a warning must not be able
    to cost someone their work. Both rules come from
    ``_release.check_editable_drift``, which learned them the hard way.
    """
    return f"git -C {repo} pull --ff-only" if repo else "git pull --ff-only"


def _editable_currency(
    check, dist, ahead_behind, behind_upstream, repo, metadata, latest
) -> Finding:
    """The CONTENT probe. The version string is deliberately ignored here.

    Two facts, and the second one is what makes the first readable:

    * ``ahead_behind`` is ``(ahead, behind)`` of the working tree vs its own
      latest release tag, from :func:`_editable.editable_ahead_behind`.
    * ``behind_upstream`` is how many commits the TRACKING REMOTE has that
      HEAD lacks, from :func:`_editable.editable_behind_upstream`.

    ``behind > 0`` against the tag asserts one thing only: *the tag is not in
    HEAD's history*. It does NOT mean the checkout is out of date, because
    release tags are cut on ``main`` while development happens on
    ``develop`` — so a perfectly current ``develop`` is permanently behind a
    tag it will never contain. That is not a hypothetical: sac's ``develop``
    measured ``+46/-3`` against ``v0.27.0`` while sitting exactly level with
    ``origin/develop``, and this check told the operator STALE and handed him
    ``git pull --rebase``. He ran it, git said "Already up to date", and the
    identical warning came back — because ``origin/develop`` does not carry
    those commits and no pull could ever bring them. A warning whose own
    remedy cannot clear it is a warning people stop reading.

    So STALE is decided on ``behind_upstream`` ALONE — the one gap a pull
    closes. The tag distance annotates, downgrades, and is reported in
    ``data``; it never raises the alarm by itself. Being AHEAD of the last
    release is the normal, healthy state of a development branch and has
    never been stale.

    The frozen ``metadata`` being behind ``latest`` PyPI is EXPECTED for an
    editable checkout and is emphatically NOT stale either — that is the
    other false positive this branch exists to refuse. So it never appears as
    a remedy, and never as STALE.
    """
    ahead, behind = ahead_behind if ahead_behind is not None else (None, None)
    data = {
        "install_kind": "editable",
        "ahead": ahead,
        "behind": behind,
        "behind_upstream": behind_upstream,
        "metadata_version": metadata,
        "pypi_latest": latest,
    }

    # -- the only axis a pull can act on ---------------------------------
    if behind_upstream:
        return Finding(
            check=check,
            state=Currency.STALE,
            summary=(
                f"editable checkout is {behind_upstream} commit(s) BEHIND "
                f"its tracking remote"
            ),
            remedy=_pull_remedy(repo),
            detail=(
                "Positively behind commits the tracking remote ALREADY HAS, "
                "so a fast-forward pull closes this gap and clears the "
                "finding. NEVER `pip install -U`, which would replace the "
                "editable checkout with a wheel."
            ),
            data=data,
        )

    if ahead_behind is None:
        return _unknown(
            check,
            "editable install: no git checkout / release tag to compare "
            "against (the frozen metadata is NOT used — it is a fossil here)",
        )

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

    # -- behind the tag, but the remote has nothing to give us ------------
    if behind_upstream == 0:
        return Finding(
            check=check,
            state=Currency.FRESH,
            summary=(
                f"editable checkout is level with its tracking remote; its "
                f"latest release tag is not on this branch "
                f"(+{ahead}/-{behind} vs that tag)"
            ),
            detail=(
                "Release tags are cut on `main`, so a `develop` or "
                "topic-branch checkout is permanently 'behind' a tag that is "
                "not in its history while being exactly current with its own "
                "remote. No pull can close that distance — `origin/<branch>` "
                "does not carry those commits — so STALE here would be a "
                "false RED with a remedy that could never clear it. The "
                "distance is kept in `data` as information; closing it is a "
                "maintainer's back-merge, not an action for whoever ran this "
                "command."
            ),
            data=data,
        )

    # -- behind the tag, and nothing can say whether a pull would help ----
    return Finding(
        check=check,
        state=Currency.UNKNOWN,
        summary=(
            f"editable checkout is {behind} commit(s) behind its latest tag, "
            f"with no tracking remote to say whether a pull would bring them"
        ),
        detail=(
            "Distance from a tag cannot on its own separate 'my branch is "
            "out of date' from 'the tag was cut on another branch'. Without "
            "a resolvable upstream there is no evidence either way, and "
            "UNKNOWN is the honest answer — any remedy printed here could "
            "not be shown to change the finding."
        ),
        data=data,
    )


# ---------------------------------------------------------------------------
# assembly + name-the-binary stamping
# ---------------------------------------------------------------------------


def _optional(sources, name):
    """Call an OPTIONAL :class:`Sources` method, or ``None`` if it is absent.

    ``Sources`` is a structural Protocol consumed ACROSS package boundaries —
    sac and the other leaves build their own source objects — so a source
    written against an older release of this package simply will not have the
    newer evidence methods. Absent evidence is exactly the ``None`` those
    methods already return for "cannot see", so it degrades into the
    tri-state instead of an AttributeError that would take the CLI down.
    """
    method = getattr(sources, name, None)
    return method() if callable(method) else None


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
            behind_upstream=_optional(sources, "editable_behind_upstream"),
            repo=_optional(sources, "editable_repo"),
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
