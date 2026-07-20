# -*- coding: utf-8 -*-
"""PS-218 — CLI health-check verb naming: standardize on `doctor`.

CLI-normalization item 4 (operator-approved). Across the ecosystem the
"does it work?" health-check verb is `doctor` in the dominant (~20x)
majority of packages. `health` is retained only as a DEPRECATED ALIAS.
A leaf that ships a `health` command as its PRIMARY health-check verb —
i.e. a `health` command WITHOUT a `doctor` command anywhere in its CLI —
is non-conforming and should rename to `doctor` (keeping `health` as a
hidden deprecation alias).

Detection heuristic (static, import-free — the auditor runs on broken
trees and must never import the leaf)
--------------------------------------------------------------------
Scan every `.py` under `src/` for a *click command registration* named
`health` / `doctor`. A command registration is one of:

  - `@<group>.command("health")` / `@click.command("health")`
  - `.command(name="health")`
  - `.add_command(<obj>, "health")` / `.add_command(<obj>, name="health")`

The rule fires (PS-218) iff a `health` command is registered AND NO
`doctor` command is registered anywhere in the same tree.

Why command-*registration* and not `def health` / `def doctor`
--------------------------------------------------------------------
A bare `def health(...)` is a FALSE-POSITIVE trap: e.g. scitex-scholar's
`_django/views.py` defines `def health(request)` — a Django view, not a
CLI verb. Matching only the click-registration string (the literal
command NAME passed to `.command(...)` / `.add_command(...)`) keys on the
user-facing CLI verb and skips unrelated functions.

False-positive / false-negative notes
--------------------------------------------------------------------
- A `doctor` command registered ANYWHERE (including nested under an
  `mcp` group, e.g. `@mcp.command("doctor")`) counts as "has doctor" and
  suppresses the finding. This is intentional and conservative: it may
  under-fire when a package's only `doctor` is a sub-verb of another
  group, but it can never mis-flag a package that already speaks the
  `doctor` vocabulary.
- Severity is W (warning): leaf migration to `doctor` is in progress
  ecosystem-wide, so this tracks conformance without failing CI.
"""

from __future__ import annotations

import re
from pathlib import Path

# A click command registration whose NAME is the captured verb. Covers
# the decorator forms `@x.command("verb")` / `.command(name="verb")` and
# the imperative `.add_command(obj, "verb")` / `.add_command(obj,
# name="verb")` forms. The verb is a whole-word literal so `doctor` never
# matches `doctorate` etc.
_COMMAND_NAME_RE = re.compile(
    r"""\.command\(\s*(?:name\s*=\s*)?["'](health|doctor)["']"""
    r"""|add_command\([^)]*?(?:name\s*=\s*)?["'](health|doctor)["']""",
)


def _src_files(repo: Path) -> list[Path]:
    """Return .py files under src/ (best-effort, gitignore-naive)."""
    src = repo / "src"
    if not src.is_dir():
        return []
    return [p for p in src.rglob("*.py") if "__pycache__" not in p.parts]


def _registered_verbs(repo: Path) -> set[str]:
    """Return the set of {`health`, `doctor`} click commands the CLI registers."""
    found: set[str] = set()
    for py in _src_files(repo):
        try:
            text = py.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in _COMMAND_NAME_RE.finditer(text):
            verb = m.group(1) or m.group(2)
            if verb:
                found.add(verb)
    return found


def check_ps218_doctor_health_naming(
    repo: Path,
    violation_cls: type,
    out: list,
) -> None:
    """Append PS-218 if the leaf ships `health` as its primary health-check verb.

    Parameters
    ----------
    repo : Path
        Repository root (the dir containing `src/`).
    violation_cls : type
        The auditor's `Violation` dataclass `(rule, where, detail)`.
    out : list
        Violations are appended in place (project-auditor convention).
    """
    verbs = _registered_verbs(repo)
    if "health" not in verbs or "doctor" in verbs:
        return
    out.append(
        violation_cls(
            "PS-218",
            str(repo / "src"),
            (
                "CLI registers a `health` command but no `doctor` command. "
                "The ecosystem standard health-check verb is `doctor` "
                "(the ~20x dominant name); `health` is a DEPRECATED ALIAS. "
                "Rename the primary command to `doctor` "
                "(`@<group>.command(\"doctor\")`) and keep `health` as a "
                "hidden deprecation alias forwarding to it — mirror the "
                "scitex-dev `doctor` command / `deprecated_alias` pattern."
            ),
        )
    )


# Rule definition, CO-LOCATED with its check (merged by `_registry.py` on
# the same terms as HOOK_RULES / URL_DEP_RULES).
#
# Severity W (warning): CLI-normalization is an in-flight ecosystem
# migration — leaves adopt `doctor` gradually — so this tracks conformance
# without failing CI. Promote to E once the fleet has migrated.
#
# (code, section, message, severity, slug)
DOCTOR_HEALTH_RULES: list[tuple[str, str, str, str, str]] = [
    (
        "PS-218",
        "§1",
        (
            "CLI health-check verb is `health` without a `doctor`: the "
            "ecosystem standard is `doctor` (the ~20x dominant name); "
            "`health` is a deprecated alias only. A leaf that ships a "
            "`health` command as its PRIMARY health-check verb (no "
            "`doctor` command registered anywhere) is non-conforming. "
            "Rename to `doctor` and keep `health` as a hidden deprecation "
            "alias. Detection is static: it matches the click command "
            "NAME passed to `.command(...)` / `.add_command(...)`, so a "
            "non-CLI `def health(...)` (e.g. a Django view) is never "
            "mistaken for the verb."
        ),
        "W",
        "cli-health-verb-not-doctor",
    ),
]


# EOF
