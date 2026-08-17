#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_ecosystem/_install_kind.py

"""What a package's version number actually means in THIS environment.

WHY THIS EXISTS, measured 2026-08-16 on scitex-compute-04. Two venvs
disagreed in a way that cannot happen:

    .venv-hub              reports 0.32.1   HAS  `dev list-undelivered`
    .venv-cards-gui-proof  reports 0.39.0   LACKS `dev list-undelivered`

The verb shipped in PR #845 on 2026-08-15, so 0.32.1 cannot have it while
0.39.0 lacks it. scitex-cards, who found this: "that impossibility is the
tell — 0.32.1 having a feature that 0.39.0 lacks is not a fact about
versions, it is a fact about the question being wrong."

The question was wrong because `.venv-hub` holds an EDITABLE install. Its
`dist-info` is a snapshot written once, at install time; the code that
actually runs is whatever the working tree holds right now. The number and
the behaviour have no relationship, and nothing in
`importlib.metadata.version()` says so.

THE FAILURE THIS MAKES VISIBLE
-------------------------------
An editable install whose target directory is DELETED keeps reporting its
version happily while `import` raises. scitex-hpc measured exactly that in
their own venv on 2026-08-02 — a `.pth` pointing at a merged PR's worktree,
removed under the three-days rule — and it went unnoticed for TWENTY DAYS
because every version check stayed green.

It is not rare. Measured across 12 venvs on this host: 8 editable installs,
and one of them (`sac-imgbuild-venv` -> a deleted
`.worktrees/agent-…/src`) is broken RIGHT NOW.

WHY THE ANSWER IS THREE-VALUED
-------------------------------
Version reconciliation errs in the REASSURING direction when it cannot tell
these apart: a low version invites "upgrade it", while nothing whatsoever
invites "this number is meaningless". So the states stay separate:

    RESOLVED   a normal install; the version means what it says
    EDITABLE   the version is a fossil; what matters is the PATH, and
               whether that path still exists
    MISSING    not installed at all

and an EDITABLE whose path is gone is reported with ``target_exists=False``,
because that environment is already broken even though it answers questions
politely.

DO NOT FOLD THIS INTO ``_release._install_probe``
--------------------------------------------------
They look like duplicates — both answer "how is this package installed?" —
and merging them is the obvious tidy. It would DELETE a capability, with a
green suite and a clean diff.

    _install_probe   answers for THIS interpreter. It resolves through
                     ``importlib.metadata`` and import success, which is the
                     more robust question (does the code actually load?) and
                     is why it stays the default everywhere.
    _install_kind    answers for ANY site-packages directory BY PATH. It
                     reads ``.pth`` files and never imports, so it can
                     inspect venvs the calling process is not running in.

You cannot import twelve venvs from one process, and the fleet-wide question
— "which installs ON THIS HOST are lying?" — needs exactly that. Verified
2026-08-16 from a process not running in the target venv::

    describe_install("scitex-agent-container",
                     Path(".../sac-imgbuild-venv/lib/python3.12/site-packages"),
                     version_of=...)
    -> EDITABLE, target_exists=False, is_broken=True

`_install_probe` cannot produce that row for a foreign venv at all.

The split is by SCOPE, not by duplication. Recorded here because the fold was
proposed on this package's own card and withdrawn only after measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

__all__ = ["InstallKind", "InstallFacts", "describe_install"]

#: setuptools/pip write one of these next to the package in site-packages.
#: Both spellings are live on this host: `__editable__.<name>-<ver>.pth`
#: (pip) and `_editable_impl_<name>.pth` (uv).
_EDITABLE_STEMS = ("__editable__", "_editable_impl_")

_PATH_IN_PTH = re.compile(r"(/[^\s'\"]+)")


class InstallKind(str, Enum):
    """How a distribution is present, if at all."""

    RESOLVED = "resolved"
    EDITABLE = "editable"
    MISSING = "missing"


@dataclass(frozen=True)
class InstallFacts:
    """Everything a caller needs to decide whether a version means anything.

    `version` is deliberately NOT the whole answer. For an EDITABLE install
    it is the install-time fossil, and reporting it alone is what let a
    broken venv look tidy for twenty days.
    """

    distribution: str
    kind: InstallKind
    version: str | None = None
    #: EDITABLE only: the source tree the .pth points at.
    target: Path | None = None
    #: EDITABLE only: whether that tree still exists. False means `import`
    #: fails NOW, whatever `version` says.
    target_exists: bool | None = None

    def __post_init__(self) -> None:
        if self.kind is InstallKind.EDITABLE and self.target is None:
            raise ValueError(
                "InstallKind.EDITABLE requires a target path: an editable "
                "install whose target is unknown is exactly the case this "
                "type exists to stop being reported as a plain version."
            )
        if self.kind is not InstallKind.EDITABLE and self.target is not None:
            raise ValueError(
                f"target is meaningful only for EDITABLE, not {self.kind}."
            )

    @property
    def version_is_meaningful(self) -> bool:
        """False when the number describes a different moment than the code."""
        return self.kind is InstallKind.RESOLVED

    @property
    def is_broken(self) -> bool:
        """True when the environment answers questions but cannot import."""
        return self.kind is InstallKind.EDITABLE and self.target_exists is False


def _editable_target(site_packages: Path, dist: str) -> Path | None:
    """The source tree an editable install for `dist` points at, if any."""
    module = dist.replace("-", "_")
    for entry in sorted(site_packages.glob("*.pth")):
        stem = entry.name
        if not stem.startswith(_EDITABLE_STEMS):
            continue
        if module not in stem.replace("-", "_"):
            continue
        try:
            text = entry.read_text(errors="replace")
        except OSError:
            continue
        found = _PATH_IN_PTH.search(text)
        if found:
            return Path(found.group(1))
    return None


def describe_install(
    distribution: str,
    site_packages: Path,
    *,
    version_of,
) -> InstallFacts:
    """Classify how `distribution` is installed under `site_packages`.

    `version_of` is injected rather than imported so this can be tested
    against a real directory tree without monkeypatching importlib —
    monkeypatch is banned ecosystem-wide, and a fixture that mutates import
    machinery is harder to trust than one that hands in a function.
    """
    target = _editable_target(site_packages, distribution)
    try:
        version = version_of(distribution)
    except Exception:  # stx-allow: fallback (reason: absent dist is a state)
        version = None

    if target is not None:
        return InstallFacts(
            distribution=distribution,
            kind=InstallKind.EDITABLE,
            version=version,
            target=target,
            target_exists=target.exists(),
        )
    if version is None:
        return InstallFacts(distribution=distribution, kind=InstallKind.MISSING)
    return InstallFacts(
        distribution=distribution, kind=InstallKind.RESOLVED, version=version
    )


# EOF
