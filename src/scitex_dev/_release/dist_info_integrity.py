#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dist-info-count install-integrity check for the ecosystem version report.

A VERSION STRING IS NOT EVIDENCE THE FIX RUNS. When TWO ``*.dist-info``
directories for a single distribution are visible at once (e.g.
``scitex_cards-0.17.9.dist-info`` AND ``scitex_cards-0.17.10.dist-info``),
WHICH ONE ``importlib.metadata`` resolves is UNSPECIFIED. It walks
``sys.path`` entries in order and takes the FIRST dist-info whose name
matches — no version comparison, no tie-break of any kind. The winner is a
property of path and directory ITERATION ORDER, not of version order, and it
goes BOTH WAYS. Measured 2026-07-29 on three hosts:

* ``scitex-dev``, two complete dist-infos in one real directory
  (``0.38.0`` written by pip, ``0.38.1`` written by uv) →
  ``version("scitex-dev")`` resolved **0.38.0**, the OLDER.
* ``scitex-cards``, two complete dist-infos in one directory → resolved the
  OLDER.
* ``scitex-cards``, ``0.17.9`` in a base layer beneath a ``0.17.10``
  overlay → ``version("scitex-cards")`` returned **0.17.10**, the NEWER
  (resolved dist-info ``scitex_cards-0.17.10.dist-info``; the console
  script agreed; all visible versions ``['0.17.10', '0.17.9']``).

The CONSEQUENCE is identical in every direction and is the point: the
REPORTED version need not describe the FILES THAT ACTUALLY RUN — stale code
can run while every version check says "current", and it can equally run
under a stale-looking version string. Do not reason about which duplicate
will win, and never build a repair on that reasoning. The only trustworthy
state is exactly one. This has bitten the fleet repeatedly.

This module is the package-agnostic guard: count the INSTALLED distributions
claiming a name — see :func:`_is_installed_dist_info` for why a ``*.dist-info``
NAME MATCH is not one — and treat any count other than 1 as a distinct
condition:

* ``count == 1`` — clean install, no finding.
* ``count == 0`` — not installed here (separate condition; NOT the double
  error — do not conflate).
* ``count  > 1`` — DIRTY INSTALL / half-upgrade. This is an ERROR, reported
  distinctly from an ordinary version mismatch.

The repair is encoded in :data:`AMBIGUOUS_METADATA_REMEDY`, and every command
in it was RUN before being recommended (2026-07-29), except where explicitly
labelled INFERRED. It leads with how to tell THREE cases apart, because a
remediation that prescribes one action for all of them is what pushes people
to disarm the check instead of using it:

* CASE 1 — EMPTY RESIDUE (fix: ``rmdir``, removes nothing).
* CASE 2 — TWO COMPLETE INSTALLS in the SAME WRITABLE DIRECTORY (fix: delete
  the stale dist-info DIRECTORY, or ``pip uninstall`` to exhaustion then
  install once).
* CASE 3 — the stale dist-info lives in a READ-ONLY LOWER OVERLAY LAYER.
  CASE 2's ``rm -rf`` does NOT transfer: it cannot remove a lower-layer entry,
  only mask it in this container's upper layer, so the image keeps shipping
  two dist-infos and every fresh container starts broken. Fix the IMAGE.
  (Overlay mechanics here are INFERRED, not measured — see the case text.)

CORRECTION, 2026-07-29 — this module previously asserted that
``pip install --force-reinstall`` does NOT fix a double install. Measured, it
does remove a prior dist-info: it uninstalls the ONE installation pip resolves
before installing (3 dist-infos → one run → 2 left; 2 → one run → 1). What is
true is narrower: it clears one duplicate per run, not all of them, so the
count must be re-checked afterwards rather than assumed converged.

CORRECTION, 2026-07-29 (second) — this module and its remediation previously
stated that ``importlib.metadata`` "picked the OLDER one". That was ONE
measurement on ONE setup generalised into a rule. A third host measured the
NEWER winning. Resolution when a distribution is duplicated is UNSPECIFIED,
never "the older": saying "the older" invites a reader to reason about which
one wins and build a repair on that reasoning.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_DIST_INFO_SUFFIX = ".dist-info"

# --- Remediation -------------------------------------------------------------
# A remediation that prescribes the SAME action for a non-problem and a real
# problem is how a correct check gets disarmed fleet-wide (an agent hit this
# check, had no non-destructive route out, and reached for the gate's env
# bypass). Every command below was RUN on 2026-07-29 against throwaway venvs
# holding coexisting scitex-cards dist-infos (0.17.8/0.17.9/0.17.10) over one
# package tree; the measured outcome is stated next to each. Composed from
# named parts so tests can pin the residue branch independently of the
# double-install branch.

_REMEDY_IDENTIFY = """\
FIRST, TELL THE THREE CASES APART — they have DIFFERENT, partly OPPOSITE fixes,
and the fix for one DAMAGES or NO-OPS in another:
    ls -A <each dist-info dir>        # lists the directory's CONTENTS
Judge by CONTENTS, never by directory SIZE. On an overlay filesystem (any
container) a directory passed through from the LOWER layer reports `size 0`
in `ls -la` while holding a complete 7-entry dist-info. Directory size is not
an emptiness test; `ls -A` is."""

_REMEDY_CASE_RESIDUE = """\
CASE 1 — one of them lists NOTHING (an EMPTY DIRECTORY): that one is
filesystem RESIDUE, not an install. It holds no distribution and no files, so
the correct fix removes nothing:
    rmdir <the empty dist-info dir>
`rmdir` deletes zero files and REFUSES to run unless the directory really is
empty, so it cannot damage a live install."""

_REMEDY_CASE_DOUBLE = """\
CASE 2 — both list METADATA and RECORD, in the SAME WRITABLE DIRECTORY: TWO
COMPLETE INSTALLS coexist. This is the real defect.
WHICH DIST-INFO WINS IS UNSPECIFIED. importlib.metadata walks sys.path in
order and takes the FIRST name match — no version comparison, no tie-break —
so the winner follows path and directory ITERATION ORDER, not version order.
It goes BOTH WAYS: measured 2026-07-29 on three hosts, two resolved the OLDER
dist-info (scitex-dev 0.38.0 over 0.38.1; scitex-cards) and one resolved the
NEWER (scitex-cards 0.17.10 over a base-layer 0.17.9). The consequence is the
same either way — THE REPORTED VERSION MAY NOT DESCRIBE THE FILES THAT
ACTUALLY RUN, in either direction. Do not predict the winner and do not build
a repair on predicting it.
FIX (SAME-LAYER DUPLICATE ONLY — this does NOT transfer to CASE 3): with ONE
package tree on disk, delete the STALE dist-info DIRECTORY only (metadata, no
payload files):
    python -c "import <module>; print(<module>.__file__)"   # confirm ONE tree
    rm -rf <site-packages>/<name>-<stale-version>.dist-info
Measured: leaves a working install — correct version, zero RECORD-listed files
missing, console scripts intact.
DO NOT clear it with a SINGLE `pip uninstall`. Both RECORDs name the SAME
files, so uninstalling one deletes the files the other still claims: measured,
that left 1 dist-info with 321 RECORD-listed files missing and the console
scripts gone, while `import` still silently succeeded as a namespace package.
If you use pip at all, run `pip uninstall {dist}` REPEATEDLY until it reports
"not installed" (measured: 2 passes), THEN install once. Stopping halfway is
worse than the state you started in."""

_REMEDY_FORCE_REINSTALL = """\
ABOUT `--force-reinstall`: it removes only the ONE installation pip currently
resolves, so it does not sweep duplicates. Measured: 3 dist-infos -> 1 run ->
2 left. It is not a one-shot fix; if you use it, re-check the count afterwards
rather than assuming it converged."""

_REMEDY_READONLY_LAYER = """\
CASE 3 — THE STALE dist-info LIVES IN A READ-ONLY LOWER OVERLAY LAYER (a base
image beneath a container's overlay). This is a DIFFERENT case with a
DIFFERENT fix, not a footnote to CASE 2. CASE 2's `rm -rf` DOES NOT TRANSFER
here: it cannot remove a lower-layer entry at all. It only writes a whiteout
in THIS container's own upper layer, so the container looks repaired while the
IMAGE still ships two dist-infos — every fresh container starts broken again,
and the "fix" evaporates on restart. FIX IT IN THE IMAGE: rebuild the layer so
it carries exactly one dist-info. Do not `rm -rf` your way out of it.
THE TELL: after deleting, a FRESH container from the SAME image still shows
two dist-infos. If the duplicate comes back on every start, you are in CASE 3,
not CASE 2.
INFERRED, NOT MEASURED — the overlay mechanics in this case are reasoned from
overlayfs semantics, not reproduced here: this container cannot construct the
shape (`mount -t overlay` refuses without superuser and `mknod` fails, CapEff
0000000000000000). Treat CASE 3 as a case to CHECK, not as a measured
result."""

#: The full duplicate-dist-info remediation, shared by this module's report
#: verdict and by ``scitex_dev.staleness``'s CURRENCY gate so the two can never
#: drift apart. ``{dist}`` is the distribution name, filled at the use site.
AMBIGUOUS_METADATA_REMEDY = "\n".join(
    (
        _REMEDY_IDENTIFY,
        _REMEDY_CASE_RESIDUE,
        _REMEDY_CASE_DOUBLE,
        _REMEDY_READONLY_LAYER,
        _REMEDY_FORCE_REINSTALL,
    )
)

#: Back-compat alias — the pre-2026-07-29 name for the same remediation.
DOUBLE_INSTALL_REMEDY = AMBIGUOUS_METADATA_REMEDY

#: Truth-in-labeling note for any report that prints a version-derived claim.
DIST_INFO_NOTE = (
    "Versions come from importlib.metadata — a dist-info CLAIM, not proof of "
    "the code that will actually run. Per-package 'dist_info_count' guards "
    "this: a count != 1 means the reported version cannot be trusted. With "
    "duplicates, which dist-info wins is UNSPECIFIED — sys.path is walked in "
    "order and the first name match wins, with no version preference — so the "
    "reported version may be the newer OR the older, and either way need not "
    "describe the files on disk."
)


def _normalize(distribution: str) -> str:
    """Escape a project name to its dist-info stem form.

    Runs of ``-_.`` collapse to a single ``_`` and the result is lowercased,
    so ``scitex-cards`` and ``scitex_cards`` both map to ``scitex_cards``
    (matching the ``scitex_cards-*.dist-info`` naming pip writes).
    """
    return re.sub(r"[-_.]+", "_", str(distribution)).strip("_").lower()


def _is_installed_dist_info(path: Path) -> bool:
    """True when ``path`` is a REAL installed distribution's dist-info.

    A NAME MATCH IS NOT EVIDENCE OF AN INSTALL. Two INDEPENDENT conditions
    must both hold, because on an overlay filesystem (every containerised
    agent) at least three different things can occupy a ``*.dist-info``
    name and a bare name-match renders them identically:

    1. IT MUST ACTUALLY BE A DIRECTORY. An overlayfs WHITEOUT — the marker
       an upper layer writes when it deletes an entry present in a lower
       layer — is a character-special device node (major 0, minor 0), not a
       directory. ``Path.is_dir()`` stats the entry and tests ``S_ISDIR``,
       so it is False for a whiteout; the TYPE test, not the name, rejects
       it.
    2. IT MUST CONTAIN A ``METADATA`` ENTRY. A dist-info directory with no
       METADATA is not an installed distribution — it is filesystem
       residue. ``pip uninstall`` removes a dist-info's FILES; on an
       overlay the now-empty DIRECTORY can survive as an entry showing
       through from the lower layer.

    DELIBERATE DECISION — a PRESENT-BUT-UNREADABLE ``METADATA`` COUNTS.
    The discriminator is EXISTENCE, not parseability. "Absent" means
    residue (a non-problem); "present but unreadable / truncated /
    malformed" means a CORRUPT install (a real problem the operator must
    see). Collapsing those two verdicts would let a genuinely corrupt
    install vanish from the report through the same door residue leaves
    by. So: ``FileNotFoundError`` disqualifies; ANY other ``OSError``
    (EACCES, EIO, ELOOP …) still counts, and the contents are never parsed
    here.
    """
    if not path.is_dir():
        return False
    try:
        os.stat(path / "METADATA")
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


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
        Number of matching INSTALLED distributions (0 = not installed here;
        1 = clean; > 1 = dirty / half-upgraded install). Entries that merely
        carry a ``*.dist-info`` NAME but are not installs — an empty residue
        directory, an overlayfs whiteout node — are excluded; see
        :func:`_is_installed_dist_info`.
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
            if not _is_installed_dist_info(child):
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
            f"{distribution}: DIRTY INSTALL — {count} installed distributions "
            f"claim this name (expected exactly 1). WHICH ONE "
            f"importlib.metadata resolves is UNSPECIFIED: sys.path is walked "
            f"in order and the FIRST name match wins, with no version "
            f"preference — so the winner follows path iteration order, not "
            f"version order, and measured on three hosts it went BOTH WAYS "
            f"(two resolved the OLDER dist-info, one the NEWER). The reported "
            f"version therefore may not describe the files that actually run, "
            f"in either direction, while every version check says 'current'.\n"
            + AMBIGUOUS_METADATA_REMEDY.format(dist=distribution)
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
