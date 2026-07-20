# -*- coding: utf-8 -*-
"""PS-219 — CLI version surface: standardize on the `--version` / `-V` flag.

CLI-normalization item 5 (operator-approved). The ecosystem standard for
"print the version" is the `--version` / `-V` FLAG (click's
`@click.version_option(...)` or an explicit `--version` option), NOT a
`version` SUBCOMMAND. A leaf that exposes version ONLY as a subcommand is
non-conforming and should move to the flag.

Detection heuristic (static, import-free — the auditor runs on broken
trees and must never import the leaf)
--------------------------------------------------------------------
Scan every `.py` under `src/` and compute two facts:

  1. version_flag_present — the CLI already offers the flag. TRUE if any
     file mentions `version_option` OR the literal string `--version`
     anywhere in the CLI source.
  2. version_subcommand_present — a *click command registration* whose
     NAME is `version`:
       - `@<group>.command("version")` / `@click.command("version")`
       - `.command(name="version")`
       - `.add_command(<obj>, "version")` / `.add_command(<obj>, name="version")`

The rule fires (PS-219) iff a `version` subcommand is registered AND the
`--version` flag is ABSENT.

Why the flag presence is the exemption (critical — no false positive on
`--version`)
--------------------------------------------------------------------
The canonical migration END-STATE keeps BOTH: a `--version` flag as the
real surface AND a HIDDEN `version` subcommand that just prints a
deprecation error redirecting to `--version` (this is exactly what
scitex-io ships: `@click.version_option(__version__, "--version", "-V")`
alongside a `hidden=True` `version` stub). Such a package is CONFORMING,
so a naive "any `version` subcommand is bad" rule would false-positive on
the very exemplar of the desired state. Gating on the presence of the
`--version` flag / `version_option` guarantees we NEVER mis-flag a
package that has already adopted the flag — the flag literal (`--version`
/ `version_option`) can never be mistaken for a subcommand because the
subcommand signal requires an explicit `.command(...)` / `.add_command`
registration with the literal name `version`.

The trade-off is a deliberate false-NEGATIVE bias: a leaf whose only
version surface is a subcommand, but whose help text merely *mentions*
`--version` in prose, is skipped. That is acceptable — the task
explicitly prefers under-firing to any false positive on `--version`.

Severity is W (warning): leaf migration is in progress ecosystem-wide.
"""

from __future__ import annotations

import re
from pathlib import Path

# The `--version` flag / version_option surface. Presence of either token
# anywhere in the CLI source EXEMPTS the package (see module docstring).
_FLAG_RE = re.compile(r"version_option|--version")

# A click command registration whose NAME is `version`. Covers the
# decorator forms `@x.command("version")` / `.command(name="version")` and
# the imperative `.add_command(obj, "version")` / `.add_command(obj,
# name="version")` forms. Whole-word literal, so it never matches
# `versionize` etc.
_VERSION_SUBCOMMAND_RE = re.compile(
    r"""\.command\(\s*(?:name\s*=\s*)?["']version["']"""
    r"""|add_command\([^)]*?(?:name\s*=\s*)?["']version["']""",
)


def _src_files(repo: Path) -> list[Path]:
    """Return .py files under src/ (best-effort, gitignore-naive)."""
    src = repo / "src"
    if not src.is_dir():
        return []
    return [p for p in src.rglob("*.py") if "__pycache__" not in p.parts]


def check_ps219_version_flag(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-219 if the leaf exposes `version` only as a subcommand.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `src/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    flag_present = False
    subcommand_present = False
    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        if not flag_present and _FLAG_RE.search(text):
            flag_present = True
        if not subcommand_present and _VERSION_SUBCOMMAND_RE.search(text):
            subcommand_present = True
        if flag_present:
            # The flag exempts the whole package — stop early.
            return
    if subcommand_present and not flag_present:
        out.append(
            violation_cls(
                "PS-219",
                str(repo / "src"),
                (
                    "CLI exposes version via a `version` SUBCOMMAND but has "
                    "no `--version` / `-V` flag. The ecosystem standard is "
                    "the flag: `@click.version_option(__version__, "
                    "\"--version\", \"-V\")` (or an explicit `--version` "
                    "click option). Move the version surface to the flag; "
                    "if you keep `version` at all, make it a hidden "
                    "deprecation alias that redirects to `--version`."
                ),
            )
        )


# Rule definition, CO-LOCATED with its check (merged by `_registry.py` on
# the same terms as HOOK_RULES / URL_DEP_RULES).
#
# Severity W (warning): CLI-normalization is an in-flight ecosystem
# migration. The check is engineered to NEVER false-positive on a package
# that already ships `--version` (the flag presence is the exemption), so
# W here reflects migration-in-progress, not false-positive risk.
#
# (code, section, message, severity, slug)
VERSION_FLAG_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-219",
        "§1",
        (
            "CLI version surface is a `version` SUBCOMMAND instead of the "
            "`--version` / `-V` flag: the ecosystem standard is the flag "
            "(`@click.version_option` / an explicit `--version` option). "
            "A leaf that exposes version ONLY as a subcommand (no "
            "`--version` flag anywhere) is non-conforming — move to the "
            "flag and keep `version` only as a hidden deprecation alias. "
            "Detection gates on the presence of the `--version` / "
            "`version_option` token, so a package that already ships the "
            "flag (even alongside a hidden `version` deprecation stub, as "
            "scitex-io does) is NEVER flagged."
        ),
        "W",
        "cli-version-subcommand-not-flag",
    ),
]


# EOF
