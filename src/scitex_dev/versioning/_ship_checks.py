#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: scitex_dev/versioning/_ship_checks.py

"""The four "did it actually ship, and is it actually running?" checks.

Split out of :mod:`._checks` (which keeps the install-currency dispatch and
report assembly) so each file has one cohesive responsibility. These four are
domain-neutral: given the recorded facts, they return pure
:class:`~scitex_dev.versioning._model.Finding` verdicts with no I/O.

Each fails in a DIFFERENT way and none subsumes another:

* ``ghost-tag``            — a tag exists, PyPI has no such release.
* ``running-vs-installed`` — installed newer than what the live daemon runs.
* ``release-run``          — the release workflow ended in failure.
* ``symbol-probe``         — a fix we KNOW shipped is absent from loaded code.
"""

from __future__ import annotations

from . import _version
from ._model import Currency, Finding
from ._symbols import probe as _default_probe

__all__ = [
    "check_ghost_tags",
    "check_release_runs",
    "check_running_vs_installed",
    "check_symbols",
]

# A run that has not finished yet says nothing about whether it will ship.
_TERMINAL = "completed"


def _unknown(check: str, why: str) -> Finding:
    """UNKNOWN carries its reason. 'I don't know' is only useful with a
    'because'."""
    return Finding(check=check, state=Currency.UNKNOWN, summary=why)


def check_ghost_tags(tags, released) -> Finding:
    """A tag with no PyPI release: ``git tag`` succeeded, shipping did not.

    Keys on the HEAD (newest) tag:

    * head tag not on PyPI => STALE. The last thing we tried to ship did not.
    * head tag published, older ghosts behind it => FRESH, but every ghost
      is still NAMED. A superseded ghost has no remedy, and an alarm with no
      remedy is noise that gets the whole check switched off.

    Self-cleaning: a deliberately-abandoned tag stops being the head as soon
    as a later version ships, and goes quiet on its own.
    """
    check = "ghost-tag"
    if tags is None:
        return _unknown(check, "no git checkout — cannot read release tags")
    if released is None:
        return _unknown(check, "PyPI unreachable — cannot tell what shipped")
    if not tags:
        return _unknown(check, "no release tags found")

    published = {k for k in (_version.parse(v) for v in released) if k is not None}
    ordered = sorted(
        ((_version.parse(t), t) for t in tags if _version.parse(t) is not None),
        key=lambda pair: pair[0],
    )
    if not ordered:
        return _unknown(check, "no parseable release tags")

    ghosts = [tag for key, tag in ordered if key not in published]
    head_key, head_tag = ordered[-1]
    head_is_ghost = head_key not in published

    data = {
        "ghosts": ghosts,
        "head_tag": head_tag,
        "head_is_ghost": head_is_ghost,
        "pypi_latest_published": _version.latest(released),
    }

    if head_is_ghost:
        return Finding(
            check=check,
            state=Currency.STALE,
            summary=(
                f"GHOST TAG: {head_tag} is tagged but NEVER reached PyPI "
                f"(newest published: {_version.latest(released) or 'none'})"
            ),
            remedy="gh run list   # then re-run the failed release, or re-tag",
            detail=(
                "The tag exists, so the release LOOKS done. It is not: "
                "nothing was published. Anyone who assumes this fix is live "
                "is wrong, and will re-diagnose an already-fixed bug."
            ),
            data=data,
        )

    if ghosts:
        return Finding(
            check=check,
            state=Currency.FRESH,
            summary=(
                f"head tag {head_tag} published OK; "
                f"{len(ghosts)} older tag(s) never shipped and were "
                f"superseded: {' '.join(ghosts)}"
            ),
            detail=(
                "Superseded ghosts: each exists in git with no PyPI release. "
                "A later version did ship, so there is nothing to fix and no "
                "alarm is raised — but they are why the tag list cannot be "
                "trusted as a record of what shipped."
            ),
            data=data,
        )

    return Finding(
        check=check,
        state=Currency.FRESH,
        summary=f"every release tag reached PyPI (head: {head_tag})",
        data=data,
    )


def check_running_vs_installed(daemon_started_at, installed_at, *, unit) -> Finding:
    """Is a live daemon still executing code from before the last upgrade?

    Installed is not running. ``pip install -U`` rewrites files on disk; it
    cannot reach into a running process and swap the modules it imported at
    boot. Until the daemon restarts, the upgrade has changed nothing.
    """
    check = "running-vs-installed"
    if not unit:
        return _unknown(check, "no daemon unit configured for this package")
    if daemon_started_at is None:
        return _unknown(check, f"{unit} is not running (or not under systemd)")
    if installed_at is None:
        return _unknown(check, "cannot determine when the package was installed")

    if installed_at <= daemon_started_at:
        return Finding(
            check=check,
            state=Currency.FRESH,
            summary=f"{unit} started after the last install — running current code",
            data={"daemon_started_at": daemon_started_at, "installed_at": installed_at},
        )

    lag_h = (installed_at - daemon_started_at) / 3600.0
    return Finding(
        check=check,
        state=Currency.STALE,
        summary=(
            f"{unit} is RUNNING PRE-UPGRADE CODE — it started "
            f"{lag_h:.1f}h before the package was last installed"
        ),
        remedy=f"systemctl --user restart {unit}",
        detail=(
            "The package on disk was upgraded while this daemon was already "
            "running. Python does not reload modules in a live process, so "
            "the daemon is still executing the OLD code and will keep doing "
            "so until it is restarted. The version string reports the NEW "
            "version the whole time, which is why it cannot answer this."
        ),
        data={
            "daemon_started_at": daemon_started_at,
            "installed_at": installed_at,
            "lag_hours": lag_h,
        },
    )


def check_release_runs(runs) -> Finding:
    """Did the most recent finished release run actually succeed?

    Anything not ``success`` — ``failure``, ``cancelled``, ``timed_out`` —
    shipped nothing, and leaves a tag behind with no PyPI release. Treating
    "not success" as one class is not pedantry; it is the real cases.
    """
    check = "release-run"
    if runs is None:
        return _unknown(check, "gh unavailable — cannot read release runs")

    finished = [r for r in runs if (r or {}).get("status") == _TERMINAL]
    if not finished:
        return _unknown(check, "no completed release runs found")

    last = finished[0]
    conclusion = last.get("conclusion")
    ref = last.get("headBranch") or "?"
    if conclusion == "success":
        return Finding(
            check=check,
            state=Currency.FRESH,
            summary=f"last release run ({ref}) succeeded",
            data={"conclusion": conclusion, "ref": ref, "url": last.get("url")},
        )

    return Finding(
        check=check,
        state=Currency.STALE,
        summary=f"last release run ({ref}) ended in {conclusion!r} — NOTHING SHIPPED",
        remedy=f"gh run view {last.get('url') or ''}".strip(),
        detail=(
            "The release pipeline is test -> build -> publish -> release. A "
            "non-success conclusion means build/publish never ran, so the tag "
            "exists with no PyPI release behind it."
        ),
        data={"conclusion": conclusion, "ref": ref, "url": last.get("url")},
    )


def check_symbols(expectations, prober=_default_probe) -> Finding:
    """Are the fixes we KNOW shipped actually present in the loaded code?

    The check that cannot be fooled by a number. Each expectation names a
    symbol that exists only in fixed code; ``hasattr`` is asked of the module
    object in the running interpreter.
    """
    check = "symbol-probe"
    if not expectations:
        return _unknown(check, "no symbol expectations registered")

    missing, present, unknown = [], [], []
    for exp in expectations:
        result = prober(exp)
        if result is True:
            present.append(exp)
        elif result is False:
            missing.append(exp)
        else:
            unknown.append(exp)

    if missing:
        first = missing[0]
        return Finding(
            check=check,
            state=Currency.STALE,
            summary=(
                f"{len(missing)} known fix(es) MISSING from the loaded code: "
                + ", ".join(e.dotted for e in missing)
            ),
            remedy="pip install -U   # then restart long-lived processes",
            detail=(
                "Probed by symbol, not by version string. "
                + first.why
                + f"  (expected since {first.since})"
            ),
            data={
                "missing": [e.dotted for e in missing],
                "present": [e.dotted for e in present],
                "unknown": [e.dotted for e in unknown],
            },
        )

    if not present:
        return _unknown(check, "no symbol could be probed")

    return Finding(
        check=check,
        state=Currency.FRESH,
        summary=f"all {len(present)} probed fix(es) present in the loaded code",
        data={
            "present": [e.dotted for e in present],
            "unknown": [e.dotted for e in unknown],
        },
    )


# EOF
