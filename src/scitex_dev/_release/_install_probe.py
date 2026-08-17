#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Timestamp: 2026-07-12
# File: scitex_dev/_release/_install_probe.py

"""Verify an install BY CONTENT — ``importlib.metadata.version()`` can lie.

WHY THIS EXISTS (incident 2026-07-12)
-------------------------------------
Every drift check in this package ultimately calls
:func:`scitex_dev._release.versions.get_version_installed`, which returns
``importlib.metadata.version(pkg)``. That string is read from a ``.dist-info``
directory — and **that directory can outlive the code it describes**. When it
does, it lies confidently, permanently, and nothing reports a problem.

Three sightings, all real, two of them on the day this module was written:

* **scitex-todo's container.** An old ``pip install -e`` left an ORPHANED
  ``scitex_todo-0.7.26.dist-info`` in site-packages with NO package files beside
  it, plus a path entry pointing at the live repo. The CODE loaded fresh from the
  working tree (0.8.7); the VERSION reported 0.7.26. Thirty releases apart.
* **scitex-agent-container's container.** A dist-info baked into the image
  reports a fossil while the code is bind-mounted from host source and current.
* **2026-07-10.** A subagent's editable install DELETED ``site-packages/scitex_todo``
  and repointed the venv at its worktree. The dist-info stayed — so every version
  check reported a healthy install **with no code behind it**.

WHY THIS MATTERS *HERE*, IN scitex-dev SPECIFICALLY
---------------------------------------------------
scitex-dev owns the fleet's drift detection. The constitution points every agent
at ``ecosystem check-versions`` as the authority on what is deployed. **A drift
detector reading a fossilised version is a drift detector turned off:**

* FALSE ALARM — it screams "0.7.26, stale, deploy now!" at a container that is
  actually running current code, forever, until its reader learns to ignore it.
* FALSE ALL-CLEAR — it blesses a container whose metadata happens to look right
  while the code behind it is stale, missing, or from someone's abandoned
  worktree. This is the dangerous one.

It cannot distinguish the two, because it never looks at the code.

The failure family, for the record: one signal never fires (a monitor nobody
runs); one always fires (an alert on things nobody can act on); and this one —
**fires confidently and is wrong**. The third is the worst, because you *act* on
it.

THE THIRD FAILURE MODE — DISK TRUTH IS NOT PROCESS TRUTH
--------------------------------------------------------
**This probe reports what is on DISK. A long-lived process may be running
something else entirely, and no version number will ever tell you.**

scitex-dev found this while auditing the incident above, and it is the sharper
half of the lesson. Symptom: an ``update_task`` call failed for HOURS with an
old-enum validator message. A mid-session ``pip install --upgrade`` changed the
code on disk, and the failures **continued, byte-identical**. Only a full process
restart cleared them.

Neither pip nor the metadata was at fault. Python imports a module ONCE, into
``sys.modules``; upgrading the files on disk does not touch the module objects a
running process already holds. So a server can serve stale code from memory while
its disk, its ``.dist-info``, and this probe ALL report a current install — and
**not one of them is lying.** They are answering a different question than the one
that was asked. That is nastier than the fossil, because every signal is
individually true.

No version number detects this: the metadata's and the source's both describe the
DISK.

**The only reliable detector is to probe the LOADED MODULE for a symbol** — which
is what ``features`` does, because ``hasattr`` reads ``sys.modules`` and therefore
interrogates the code the process is ACTUALLY RUNNING::

    p = probe_install("scitex-cards", features={
        "post_migration_enum": "scitex_cards._model:VALID_BLOCKERS",
    })
    if not p.features["post_migration_enum"]:
        # THIS PROCESS runs pre-migration code, whatever the disk says.
        # An upgrade will NOT fix it — only a RESTART will.

The rule: **to know what a process is running, ask the process — not the package
manager.** And when the answer is "stale", the remedy is a RESTART; an upgrade
will not touch it. (That clause is the operationally useful half: scitex-dev DID
upgrade, and it changed nothing.)

An mtime-vs-process-start heuristic was tried and DELIBERATELY NOT SHIPPED: it
depends on boot-time arithmetic and clock skew, and returned a wrong answer on the
first live box it was pointed at. Shipping a flaky detector for a false-confidence
bug would be self-parody. Symbol probing is exact.

DESIGN
------
Vendored deliberately, not imported from scitex-cards. scitex-dev owns the
ecosystem conventions and must not take a dependency on a leaf package that
consumes them — the arrow points the wrong way, and scitex packages stay
independent by standing directive. The logic is ~150 lines; the coupling would
cost more than the duplication.

**Never raises.** A probe that can crash gets wrapped in ``try/except`` and
ignored — which is the disease, not the cure. Every failure returns a populated
result carrying an actionable hint.

**Unverifiable is never reported as honest.** If the probe cannot POSITIVELY
confirm that the metadata matches the code, ``trustworthy`` is False. "I could
not check" must never render as "it is fine" — that conflation is the whole bug.

**Scope: THIS interpreter only.** This module resolves through
``importlib.metadata`` and import success, so every answer it gives is about
the environment it is running in. That is deliberate and it is the more
robust question — "does the code load?" beats any inspection of install
metadata.

It does mean this module CANNOT answer for a venv it is not running in, and
that question is real: "which installs on this host are lying?" needs to walk
twelve venvs, which one process cannot import.
``_ecosystem._install_kind.describe_install`` covers that case by reading
``.pth`` files from an arbitrary site-packages path without importing
anything.

The two are split by SCOPE, not duplicated. Folding them was proposed on
2026-08-16 and withdrawn after measurement showed it would delete the
cross-venv capability — see that module's docstring for the measurement.
"""

from __future__ import annotations

import importlib
import importlib.metadata as _md
from dataclasses import dataclass, field
from pathlib import Path

#: Code lives under site-packages: it was installed FROM a built distribution,
#: so the metadata shipped alongside the code it describes. Trustworthy.
KIND_WHEEL = "wheel"
#: Code lives in a source tree OUTSIDE site-packages — an editable install, a
#: bind-mount, or a bare ``sys.path`` entry. The metadata is a SNAPSHOT taken at
#: install time and drifts freely from the code thereafter. Ask the source.
KIND_EDITABLE = "editable"
#: Metadata exists; the module CANNOT be imported. The worst case: every version
#: check "passes" against a package that is not there.
KIND_ORPHANED = "orphaned"
#: Neither metadata nor importable code. Simply not installed — NOT a lie, and
#: deliberately distinct from ``orphaned``: reporting an absent package as an
#: orphaned .dist-info would send the reader hunting for a directory that does
#: not exist. A diagnostic that is confidently wrong IS the disease treated here.
KIND_ABSENT = "absent"
#: Code imports, but nothing claims a version. Honest by omission.
KIND_UNMANAGED = "unmanaged"

_SITE_MARKERS = ("site-packages", "dist-packages")

#: Depth limit when walking up from the module toward the project's pyproject.
#: 5 covers ``<root>/src/<pkg>/__init__.py`` with room to spare; an unbounded
#: walk would climb out of the project entirely on an unusual layout.
_PYPROJECT_SEARCH_DEPTH = 5


@dataclass
class InstallProbe:
    """What the metadata claims, what the code says, and whether they agree."""

    dist: str
    kind: str
    metadata_version: str | None = None
    code_version: str | None = None
    module_path: str | None = None
    source_root: str | None = None
    honest: bool = False
    detail: str = ""
    hint: str | None = None
    #: Set when the PROBE itself failed, so a caller can tell "the install is
    #: broken" apart from "the probe is broken".
    probe_error: str | None = None
    features: dict[str, bool] = field(default_factory=dict)

    @property
    def trustworthy(self) -> bool:
        """True iff ``metadata_version`` may be used as the real version.

        The ONE question a deploy/drift check should ask before comparing
        version strings. False for an orphaned or drifted install — i.e.
        exactly when the version string would mislead.
        """
        return self.honest and self.kind in (KIND_WHEEL, KIND_EDITABLE)

    @property
    def effective_version(self) -> str | None:
        """The version actually RUNNING, as best as can be established.

        For a wheel, that is the metadata. For an editable/bound install it is
        the SOURCE's declared version — the code is what will execute, whatever
        a stale dist-info claims. ``None`` when it cannot be established at all,
        which callers must treat as unknown, never as agreement.
        """
        if self.kind == KIND_WHEEL:
            return self.metadata_version
        if self.kind == KIND_EDITABLE:
            return self.code_version or None
        return None


def _read_pyproject_version(root: Path) -> str | None:
    """The version literal from ``root/pyproject.toml`` — the source's own claim."""
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - py<3.11
        return None
    try:
        with (root / "pyproject.toml").open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, ValueError):
        return None
    project = data.get("project")
    if isinstance(project, dict):
        v = project.get("version")
        if isinstance(v, str):
            return v
    return None


def _find_source_root(module_file: Path) -> Path | None:
    cur = module_file.parent
    for _ in range(_PYPROJECT_SEARCH_DEPTH):
        if (cur / "pyproject.toml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _classify(module_file: Path) -> str:
    if any(m in module_file.parts for m in _SITE_MARKERS):
        return KIND_WHEEL
    return KIND_EDITABLE


def _has_feature(target: str) -> bool:
    """True when ``module:attribute`` exists — the content-probe primitive."""
    mod_name, _, attr = target.partition(":")
    try:
        mod = importlib.import_module(mod_name)
    except Exception:  # noqa: BLE001
        return False
    return hasattr(mod, attr) if attr else True


def probe_install(
    dist: str,
    module: str | None = None,
    *,
    features: dict[str, str] | None = None,
) -> InstallProbe:
    """Probe ``dist``'s install; report whether its version string can be trusted.

    ``module`` defaults to ``dist`` with ``-`` mapped to ``_``.

    ``features`` maps a label to a ``"module:attribute"`` path that should exist
    in the version you believe is deployed — a CONTENT probe. It answers "is the
    code I think I shipped actually here?" **without trusting any version at
    all**, and it is the only check a fossilised dist-info cannot defeat::

        probe_install("scitex-cards", features={
            "v088": "scitex_cards._install_probe:probe_install",
        })

    Never raises.
    """
    mod_name = module or dist.replace("-", "_")
    probe = InstallProbe(dist=dist, kind=KIND_ORPHANED)

    try:
        probe.metadata_version = _md.version(dist)
    except _md.PackageNotFoundError:
        probe.metadata_version = None
    except Exception as exc:  # noqa: BLE001 - a probe must never crash its caller
        probe.probe_error = f"reading metadata for {dist!r} failed: {exc}"

    try:
        mod = importlib.import_module(mod_name)
    except Exception as exc:  # noqa: BLE001
        probe.honest = False
        if probe.metadata_version is None:
            probe.kind = KIND_ABSENT
            probe.detail = (
                f"{dist} is not installed: no metadata, and `import {mod_name}` "
                f"failed ({exc})."
            )
            probe.hint = (
                f"Nothing to trust and nothing to repair — the package is simply "
                f"absent. Install it if it is expected: `pip install {dist}`."
            )
            return probe
        probe.kind = KIND_ORPHANED
        probe.detail = (
            f"metadata claims {dist} {probe.metadata_version}, but "
            f"`import {mod_name}` FAILED: {exc}"
        )
        probe.hint = (
            f"ORPHANED INSTALL — the worst case: a .dist-info claims "
            f"{dist} {probe.metadata_version} with NO importable code behind it, so "
            f"every version check PASSES against a package that is not there. "
            f"Repair: `pip install --force-reinstall --no-deps {dist}`, or delete "
            f"the stale .dist-info from site-packages."
        )
        return probe

    mod_file = getattr(mod, "__file__", None)
    if not mod_file:
        probe.kind = KIND_UNMANAGED
        probe.detail = f"{mod_name} exposes no __file__ (namespace package?)"
        probe.hint = "Cannot verify by content: the module has no file path."
        return probe

    mod_path = Path(mod_file).resolve()
    probe.module_path = str(mod_path)
    probe.kind = _classify(mod_path)

    if features:
        probe.features = {
            label: _has_feature(target) for label, target in features.items()
        }

    if probe.metadata_version is None:
        probe.kind = KIND_UNMANAGED
        probe.honest = True  # nothing is claimed, so nothing can lie
        probe.detail = (
            f"{mod_name} imports from {mod_path} but has NO installed metadata "
            f"(a bare sys.path entry). No version is claimed."
        )
        probe.hint = (
            "Honest by omission, but no version is knowable. Install the package "
            "properly if its version needs to be reportable."
        )
        return probe

    if probe.kind == KIND_WHEEL:
        probe.code_version = probe.metadata_version
        probe.honest = True
        probe.detail = (
            f"{dist} {probe.metadata_version}: wheel install under site-packages; "
            f"the metadata shipped with the code beside it."
        )
        return probe

    # Editable / bind-mounted: the metadata is an install-time snapshot and the
    # code has moved on freely since. Ask the SOURCE what it actually is.
    root = _find_source_root(mod_path)
    if root is None:
        probe.honest = False
        probe.detail = (
            f"{dist} loads from the source tree {mod_path} (editable/bound), but no "
            f"pyproject.toml was found above it, so the code's real version is "
            f"UNKNOWN. Metadata claims {probe.metadata_version} — do not trust it."
        )
        probe.hint = (
            "Verify by content instead: probe for a symbol that only exists in the "
            "version you expect (see the `features` argument)."
        )
        return probe

    probe.source_root = str(root)
    probe.code_version = _read_pyproject_version(root)

    if probe.code_version is None:
        probe.honest = False
        probe.detail = (
            f"{dist} loads from {root} (editable/bound), but its pyproject.toml "
            f"declares no static version; metadata claims {probe.metadata_version}, "
            f"which cannot be confirmed."
        )
        probe.hint = (
            "Cannot confirm by content. Declare a static `project.version`, or "
            "verify with the `features` argument."
        )
        return probe

    probe.honest = probe.code_version == probe.metadata_version
    if probe.honest:
        probe.detail = (
            f"{dist} {probe.code_version}: editable/bound from {root}; the metadata "
            f"agrees with the source. The version string is trustworthy."
        )
        return probe

    probe.detail = (
        f"VERSION STRING LIES: metadata says {dist} {probe.metadata_version}, but "
        f"the code actually loaded, from {root}, is {probe.code_version}."
    )
    probe.hint = (
        f"The .dist-info is a FOSSIL — it outlived the code it describes, so every "
        f"version-based drift/deploy check against {dist} is currently meaningless: "
        f"it will cry stale at a current install, or bless a stale one. Refresh the "
        f"metadata without touching anything else:\n"
        f"    uv pip install -e {root} --no-deps   (or: pip install -e {root} --no-deps)\n"
        f"Until then, trust ONLY content checks, never the version."
    )
    return probe


def get_version_installed_verified(package: str) -> str | None:
    """The version actually RUNNING for ``package`` — content-verified.

    A drop-in for :func:`scitex_dev._release.versions.get_version_installed` that
    cannot be fooled by a fossilised ``.dist-info``:

    * wheel install      -> the metadata (it shipped with the code)
    * editable/bound     -> the SOURCE's version (the code is what executes)
    * orphaned / absent  -> ``None`` (unknown; never a confident wrong answer)

    ``None`` means "I could not establish what is running", and callers MUST
    treat it as unknown rather than as agreement. Returning a version we cannot
    stand behind is precisely the bug this module exists to kill.
    """
    return probe_install(package).effective_version


# EOF
