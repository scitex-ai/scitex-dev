#!/usr/bin/env python3
# Timestamp: 2026-07-29
# File: scitex_dev/_core/dist_info.py

"""DETECT duplicate dist-info directories. Never delete them.

Until 2026-07-29 this module's ``clean_stale_dist_info()`` read as if it did
what its name said: for every package with more than one ``*.dist-info`` in a
site dir, sort by MTIME and ``shutil.rmtree`` everything but the newest. It
was called UNCONDITIONALLY from the skills-export path, so on its face
"export skills to a directory" silently deleted package metadata from every
site-packages dir.

MEASURED FIRST, BEFORE CHANGING ANYTHING — and the measurement corrected the
diagnosis. That ``rmtree`` was UNREACHABLE. The grouping key was
``d.name.rsplit("-", 1)[0]``, and ``d.name`` still carried the
``.dist-info`` suffix, so the split landed on the hyphen inside "dist-info":
``"demo_pkg-2.0.dist-info"`` grouped under ``"demo_pkg-2.0.dist"``, VERSION
INCLUDED. Every distribution therefore landed in its own group of exactly
one, the ``len(dirs) <= 1: continue`` fired every time, and nothing was ever
deleted. Verified on a real throwaway venv seeded with two ``demo_pkg``
dist-infos in reverse mtime order: the function returned ``[]`` and all
directories survived. NOTHING IN THE FLEET WAS EVER DAMAGED BY THIS.

It is removed anyway, because the danger is real and latent: the grouping bug
is the ONLY thing disarming it, it looks like a plain typo, and the obvious
"fix" — strip the suffix before splitting — would arm an mtime-ordered
``rmtree`` inside an unrelated export path in a single line. The reasons that
made it unsafe are below and none of them depend on the bug:

1. MTIME IS NOT VERSION ORDERING. ``cp -p`` preserves mtimes, image builds
   stamp arbitrary ones, and an overlay lower-layer directory carries the
   BASE IMAGE's mtime. Sorting by mtime can therefore delete the NEWER
   distribution's metadata and keep the older — leaving a package that
   imports fine and reports the WRONG version, which is exactly the failure
   scitex-storage ran on for weeks (0.30.0 files under a 0.37.1 dist-info).
   Correct-by-luck is not correct: mtime carries no version information.
2. NAME-ONLY GLOB, NO TYPE TEST. ``glob("*.dist-info")`` matches by name. An
   overlayfs WHITEOUT is a character-special device node, not a directory,
   and matched that glob on its way into ``shutil.rmtree``.
3. A DESTRUCTIVE SIDE EFFECT ON AN UNRELATED OPERATION. Nobody exporting
   skills expects their environment's package metadata to be removed.
4. EVEN A CORRECT VICTIM CHOICE IS UNSAFE ACROSS LAYERS — AND THIS REASON IS
   INDEPENDENT OF (1). Fixing only the mtime ordering would leave it. When
   the target lives in a container's READ-ONLY BASE LAYER, ``rmtree`` cannot
   remove it; it can only mask it with a whiteout in the caller's overlay.
   The deletion then APPEARS to succeed while the base image still ships the
   duplicate, so every fresh container starts broken again — and the running
   container's metadata now silently differs from the image it was built
   from. Worse, "this overlay contains no whiteouts" is a property agents
   check before a base-image swap; a single automatic call can destroy that
   property and turn a verified-safe restart into a mismatch, reported
   nowhere above ``logger.info``.

So this module now DETECTS and REPORTS. Note that NOTHING HERE DEPENDS ON THE
EXACT OVERLAYFS SEMANTICS above: the code deletes nothing, so it cannot be
wrong about how a whiteout behaves. (The whiteout mechanics in (4) are
INFERRED from observed container behaviour, not read out of overlayfs
internals — which is precisely why no code in this module is allowed to bet
on them.)

Removal, if a caller ever genuinely needs it, must be an EXPLICIT
user-invoked verb with a dry-run default that picks its victim by the version
PARSED FROM METADATA — never by mtime — and that REFUSES when the target
cannot be truly removed in the caller's own layer rather than writing a
whiteout and reporting success. If that condition cannot be detected
reliably, the verb must refuse on any duplicate that may span layers and say
why: refusing is the correct outcome. This module deliberately provides no
such verb.
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

_DIST_INFO_SUFFIX = ".dist-info"


def _is_installed_dist_info(path: Path) -> bool:
    """True when ``path`` is a REAL installed distribution's dist-info.

    A NAME MATCH IS NOT EVIDENCE OF AN INSTALL — two independent conditions,
    both required:

    1. it must actually BE a directory (``Path.is_dir()`` stats the entry and
       tests ``S_ISDIR``, so an overlayfs whiteout — a character-special
       device node — is rejected here, by TYPE rather than by name);
    2. it must contain a ``METADATA`` entry (a dist-info directory with none
       is filesystem residue: pip removed the files and, on an overlay, the
       emptied directory survived from the lower layer).

    A PRESENT-BUT-UNREADABLE ``METADATA`` COUNTS, deliberately: absent means
    residue (a non-problem), unreadable means a CORRUPT install (a real
    problem), and collapsing the two would let corruption vanish through the
    residue door.
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


def find_duplicate_dist_infos(
    site_packages: str | Path | None = None,
) -> dict[str, list[str]]:
    """Report packages with MORE THAN ONE installed dist-info, per site dir.

    PURELY OBSERVATIONAL — this function creates, moves and deletes nothing.

    Parameters
    ----------
    site_packages:
        A single directory to inspect — the NO-MOCK test seam. ``None``
        (production) inspects every ``site.getsitepackages()`` entry.

    Returns
    -------
    dict[str, list[str]]
        Package stem -> the duplicate dist-info paths found for it, as
        strings, sorted. Packages with 0 or 1 installed dist-info are
        omitted. Entries that merely carry a ``*.dist-info`` NAME without
        being installs — empty residue directories, whiteout nodes — are
        excluded; see :func:`_is_installed_dist_info`.

    Note the grouping key strips ``.dist-info`` BEFORE splitting off the
    version. The predecessor did not, so its key kept the version and no two
    distributions ever grouped together — it could not report a duplicate,
    let alone act on one. Grouping correctly is what makes this function able
    to see anything at all; it is also why it must never be paired with a
    removal step.
    """
    if site_packages is None:
        import site

        site_dirs = (
            site.getsitepackages() if hasattr(site, "getsitepackages") else []
        )
    else:
        site_dirs = [str(site_packages)]

    duplicates: dict[str, list[str]] = {}
    for site_dir in site_dirs:
        sp = Path(site_dir)
        if not sp.is_dir():
            continue
        by_package: dict[str, list[Path]] = defaultdict(list)
        try:
            children = sorted(sp.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.name.endswith(_DIST_INFO_SUFFIX):
                continue
            if not _is_installed_dist_info(child):
                continue
            stem = child.name[: -len(_DIST_INFO_SUFFIX)]
            parts = stem.rsplit("-", 1)
            if len(parts) == 2:
                by_package[parts[0]].append(child)
        for pkg_name, dirs in by_package.items():
            if len(dirs) <= 1:
                continue
            duplicates.setdefault(pkg_name, []).extend(
                sorted(str(d) for d in dirs)
            )
    return duplicates


def report_duplicate_dist_infos(
    site_packages: str | Path | None = None,
) -> list[str]:
    """Log a WARNING for each package with duplicate dist-infos; return names.

    The non-destructive replacement for the old ``clean_stale_dist_info()``.
    A duplicate is worth SAYING OUT LOUD — an ambiguous resolver makes every
    version-derived claim untrustworthy — but it is not worth deleting
    metadata behind the caller's back.
    """
    duplicates = find_duplicate_dist_infos(site_packages)
    for pkg_name, paths in sorted(duplicates.items()):
        logger.warning(
            "duplicate dist-info for %s — %d installed distributions claim "
            "this name (%s). Version-derived claims about it cannot be "
            "trusted. NOT removing anything: choosing a victim by mtime is "
            "not version ordering and can delete the NEWER metadata. Repair "
            "it explicitly — see scitex_dev._release.dist_info_integrity for "
            "the measured remediation.",
            pkg_name,
            len(paths),
            ", ".join(Path(p).name for p in paths),
        )
    return sorted(duplicates)


def clean_stale_dist_info(
    site_packages: str | Path | None = None,
) -> list[str]:
    """DEPRECATED, AND NO LONGER DELETES ANYTHING.

    Kept only so an out-of-tree importer of the old name does not crash. It
    now delegates to :func:`report_duplicate_dist_infos`, so the RETURN VALUE
    CHANGED MEANING: it lists the packages found with duplicate dist-infos,
    NOT dist-infos removed — because none are removed. See the module
    docstring for why deleting by mtime was unsafe.
    """
    logger.warning(
        "clean_stale_dist_info() no longer removes anything (it chose its "
        "victim by mtime, which is not version ordering, and could delete "
        "the NEWER metadata). It now reports duplicates only; the returned "
        "list is packages FOUND, not directories removed."
    )
    return report_duplicate_dist_infos(site_packages)


# EOF
