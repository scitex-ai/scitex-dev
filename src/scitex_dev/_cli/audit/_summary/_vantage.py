#!/usr/bin/env python3
"""Report WHICH artifact an audit measured — its vantage point.

Every §-rule in `_audit.py` is a statement about one in-memory Click tree,
loaded from one file on disk. `importlib.metadata.entry_points()` resolves
against the INSTALLED distributions, so running the audit inside a repo
checkout still measures whatever is installed in this interpreter — which
can be an entirely different build from the tree the reader is looking at.

WHY THIS MODULE EXISTS
----------------------
On 2026-08-21 scitex-cards reported 24 of 35 findings (~69%) as false
positives, quoting a verbatim `--help` capture that showed two flags the
audit had called missing — with a negative control proving their method
could report absence.

Measured against the build reachable from the auditing side, the audit was
RIGHT: `--dry-run` and `--yes` were absent from `.params` AND from the
rendered `--help` alike. scitex-cards then re-measured and withdrew the
claim in full — the correct false-positive count was 0. The flags and
examples existed only on their branch, reached through a hardcoded
`PYTHONPATH` pointing at their worktree.

THE PATH IS THE LOAD-BEARING FIELD, NOT THE VERSION
---------------------------------------------------
The two trees they compared reported:

    audit run     0.48.0   .../scitex-cards/src/scitex_cards/__init__.py
    --help shell  0.48.0   .../.worktrees/<branch>/src/scitex_cards/__init__.py

**Identical version, different code.** A provenance line that logged only
the version would have shown `0.48.0` on both sides and let this exact
evening happen again. `module_file` is therefore the field that does the
work here; `distribution_version` is context, not identity. Any future
trimming of this report must keep the resolved path.

Both reports were accurate about different objects. Neither output named
the object it described, so no amount of re-reading either report could
surface the split — it took a third party importing both. A finding that
cannot be traced back to the artifact it was made about is not checkable,
only believable.

This module makes the audit state its vantage point in every report, so the
next disagreement is settled by reading one line instead of an evening.
"""

from __future__ import annotations

import importlib.metadata as im
import sys

__all__ = ["UNRESOLVED", "resolved_vantage", "format_vantage"]

#: Sentinel for a field that could not be resolved.
#:
#: Deliberately NOT "" or None. An empty string renders as a blank column
#: that reads like a real (empty) answer, and None renders as "None" which
#: reads like a bug; "unresolved" cannot be mistaken for a path or version
#: and states its own uncertainty at the point of use.
UNRESOLVED = "unresolved"

_FIELDS = ("entry_point", "module", "module_file", "distribution_version")


def _entry_point_value(package: str) -> str:
    """The `module:attr` string the console script points at."""
    try:
        eps = im.entry_points(group="console_scripts")
    except TypeError:  # pragma: no cover - older importlib.metadata shape
        eps = im.entry_points().get("console_scripts", [])
    for ep in eps:
        if ep.name == package:
            return ep.value
    return UNRESOLVED


def _distribution_version(package: str) -> str:
    """Installed version, tolerating dash/underscore distribution spellings."""
    for name in (package, package.replace("-", "_"), package.replace("_", "-")):
        try:
            return im.version(name)
        except Exception:
            continue
    return UNRESOLVED


def _module_of(root: object | None) -> str | None:
    """The module that DEFINED this command, never the framework's own.

    A `click.Command` is an INSTANCE, so `root.__module__` falls back to the
    class and yields `click.core` — click's installed path, not the audited
    package's. Reporting that would be worse than reporting nothing: it is a
    real, existing file, so it reads as a successful answer while pointing at
    the wrong artifact entirely. Measured 2026-08-21:

        demo.__module__            -> 'click.core'
        demo.callback.__module__   -> the defining module

    The callback is the author's own function, so it carries the honest
    module. Anything resolving into click itself is refused and the caller
    falls back to the entry-point declaration.
    """
    if root is None:
        return None
    callback = getattr(root, "callback", None)
    name = getattr(callback, "__module__", None)
    if not name:
        return None
    if name == "click" or name.startswith("click."):
        return None
    return name


def resolved_vantage(package: str, root: object | None = None) -> dict[str, str]:
    """Describe the artifact an audit of ``package`` actually measured.

    ``root`` is the resolved Click root when the caller already has one;
    passing it keeps this report describing the SAME object the findings
    were made about. Omitting it falls back to the entry-point declaration,
    which is one inference removed from the measurement.

    Every value is a string, and anything unresolvable is :data:`UNRESOLVED`
    rather than a blank that would read as an answer.
    """
    out = {field: UNRESOLVED for field in _FIELDS}
    out["entry_point"] = _entry_point_value(package)
    out["distribution_version"] = _distribution_version(package)

    mod_name = _module_of(root)
    if not mod_name and out["entry_point"] != UNRESOLVED:
        mod_name = out["entry_point"].split(":")[0] or None
    if not mod_name:
        return out

    out["module"] = mod_name
    # Read __file__ off the ALREADY-IMPORTED module rather than re-importing.
    # A fresh import could resolve to a different copy than the one that
    # produced `root`, which would defeat the entire purpose of this report.
    mod = sys.modules.get(mod_name) or sys.modules.get(mod_name.split(".")[0])
    module_file = getattr(mod, "__file__", None)
    if module_file:
        out["module_file"] = module_file
    return out


def alignment(vantage: dict[str, str], audited_path: object | None) -> str:
    """Do the audited FILES and the imported CLI OBJECTS come from one tree?

    `--path` selects which files are audited (workflows, pyproject, docs),
    but the Click objects still come from whatever this interpreter imports.
    Point `--path` at a worktree while the editable install resolves
    elsewhere and the audit silently produces a HYBRID: one tree's files
    judged against another tree's CLI.

    Measured by scitex-cards, 2026-08-21, same `--path`, same auditor, only
    PYTHONPATH changed:

        no PYTHONPATH   -> imports main checkout   35 unmasked findings
        PYTHONPATH=wt   -> imports the branch      12 unmasked findings

    The local symptom is findings that look UNFIXABLE: you add the flag on
    your branch, re-run, and it is still reported — because the run never
    read your branch.

    COMPARES PATHS, NEVER VERSIONS — and must keep doing so. The two trees
    in the incident above both reported `0.48.0`; a version comparison would
    have stayed silent across a 23-error gap. Any future change that
    "optimises" this into a version check reintroduces the exact defect this
    function exists to catch. `test_alignment_ignores_a_matching_version...`
    pins it.

    Three-valued by construction. "unknown" is a real answer here: with no
    `--path` given, or an unresolved module file, there is nothing to
    compare and saying "aligned" would be a fabricated reassurance.
    """
    module_file = vantage.get("module_file", UNRESOLVED)
    if audited_path is None or module_file == UNRESOLVED:
        return "unknown"
    try:
        from pathlib import Path

        target = Path(str(audited_path)).resolve()
        measured = Path(module_file).resolve()
    except Exception:
        return "unknown"
    return "aligned" if target in measured.parents else "mismatch"


def format_alignment(
    vantage: dict[str, str], audited_path: object | None
) -> str | None:
    """A loud line when files and objects disagree; nothing when they agree.

    Silence on "aligned" is deliberate — a warning that prints on every run
    stops being read. Silence on "unknown" is also deliberate: the vantage
    line already states what was measured, and inventing a verdict from a
    comparison that could not be made is exactly the failure this module
    exists to prevent.
    """
    if alignment(vantage, audited_path) != "mismatch":
        return None
    return (
        "# WARNING hybrid audit: files under "
        f"{audited_path}, but the CLI objects were imported from "
        f"{vantage.get('module_file', UNRESOLVED)}. CLI findings describe the "
        "IMPORTED tree, not the one you passed to --path — fixes on the "
        "audited tree will not clear them. Install that tree into this "
        "interpreter, or point PYTHONPATH at its src/."
    )


def format_vantage(vantage: dict[str, str]) -> str:
    """One human-readable line naming the measured artifact.

    Rendered next to the findings, not in a separate verbose mode: a reader
    disputing a finding needs this in the same glance as the finding.
    """
    return (
        f"# measured: {vantage.get('module_file', UNRESOLVED)} "
        f"(v{vantage.get('distribution_version', UNRESOLVED)}, "
        f"entry_point {vantage.get('entry_point', UNRESOLVED)})"
    )
