"""Audit the umbrella `scitex` pyproject.toml for exact member pins (PS-170).

The umbrella declares its members (scitex-*, figrecipe, newb, socialia, ...)
with MINIMUM versions: `"scitex-io>=0.4.0"` names the oldest release that
provides what the umbrella imports or re-exports. Library metadata states
compatibility; reproducing a release snapshot is a lock file's job.

An exact pin (`"scitex-io==0.7.0"`) is a violation:

- installing or upgrading the umbrella downgrades a newer installed member
  (`pip install -U 'scitex[all]'` once replaced scitex-dev 0.62.30 with
  0.28.0 and scitex-scholar 1.29.2 with 1.4.2);
- users who install a member directly can no longer install the umbrella
  next to a different version of it;
- every member release forces an umbrella release.

History: until scitex-dev 0.67 this audit ACCEPTED `==` and drift-checked it
against PyPI latest, which pushed the umbrella to re-pin (and re-release) on
every member release -- the very coupling above. PS-170 now flags the pin
itself and needs no network. The ecosystem-wide rule for every package is
PS-237 (`scitex-dev audit project`); this command is the umbrella-scoped
view of the same check.

Run via:

    scitex-dev ecosystem audit-umbrella-pins [PATH] [--strict]

PATH defaults to the cwd. Findings are warn-only by default (exit 0);
``--strict`` exits 1 on any exact pin. On any package other than the
umbrella (pyproject.toml `name = "scitex"`) it exits 0 silently, so it is
safe in a shared CI step.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover — 3.10 path
    import tomli as tomllib  # type: ignore[no-redef]

from packaging.requirements import InvalidRequirement, Requirement

from ._project._check_exact_pins import exact_pin

UMBRELLA_NAME = "scitex"
# The publishable ecosystem members the umbrella depends on.
_MEMBER_RE = re.compile(
    r"^(scitex-[a-z0-9-]+|figrecipe|newb|socialia|crossref-local|openalex-local)$"
)


def _requirements(project: dict) -> list[str]:
    reqs = list(project.get("dependencies", []) or [])
    for group in (project.get("optional-dependencies", {}) or {}).values():
        if isinstance(group, list):
            reqs.extend(group)
    return [r for r in reqs if isinstance(r, str)]


def audit_umbrella_pins(repo: Path) -> list[str]:
    """Return one PS-170 violation string per exact-pinned member; [] = clean.

    Only fires on the umbrella package (pyproject.toml ``name = "scitex"``);
    on any other package (or without a readable pyproject) returns ``[]``.
    Each distinct requirement string is reported once, even when it appears
    in several extras.
    """
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get(
            "project", {}
        )
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return []
    if not isinstance(project, dict) or project.get("name") != UMBRELLA_NAME:
        return []

    seen: set[str] = set()
    violations: list[str] = []
    for requirement in _requirements(project):
        if requirement in seen:
            continue
        seen.add(requirement)
        try:
            name = Requirement(requirement).name.lower()
        except InvalidRequirement:
            continue
        if name == UMBRELLA_NAME or not _MEMBER_RE.match(name):
            continue
        clause = exact_pin(requirement)
        if clause is None:
            continue
        violations.append(
            f"PS-170: {requirement} is an exact pin. Declare the oldest "
            f"{name} release that provides what the umbrella uses "
            f"({name}>=X.Y); `{clause}` downgrades newer installs and forces "
            f"an umbrella release for every {name} release."
        )
    return violations


@click.command(
    "audit-umbrella-pins",
    cls=SpecCommand,
    help_spec=CliHelp(
        summary="Flag exact `==` member pins in the umbrella pyproject.",
        description=(
            "The umbrella must declare members with minimum versions "
            "(`>=`). Each exact `==`/`===` member pin is reported as PS-170 "
            "(no network access). Warn-only by default (exit 0); --strict "
            "exits 1 on any exact pin. Only fires on the umbrella package "
            'itself (pyproject.toml `name = "scitex"`); on any other '
            "package it exits 0 silently. The ecosystem-wide rule for every "
            "package is PS-237 in `scitex-dev audit project`."
        ),
        examples=(
            Example(
                "{prog} ecosystem audit-umbrella-pins .",
                "Warn-only check of the cwd umbrella.",
            ),
            Example(
                "{prog} ecosystem audit-umbrella-pins /path/to/scitex-python --strict",
                "Release gate: fail on any exact member pin.",
            ),
        ),
    ),
)
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd,
)
@click.option(
    "--allow-network-error",
    is_flag=True,
    hidden=True,
    help="Deprecated no-op: the audit no longer queries PyPI.",
)
@click.option(
    "--strict",
    is_flag=True,
    help=(
        "Treat exact member pins as ERROR (exit 1). Default is WARN-ONLY: "
        "findings print to stderr with a WARN: prefix and the command "
        "exits 0."
    ),
)
def cli(path: Path, allow_network_error: bool, strict: bool) -> None:
    violations = audit_umbrella_pins(path)
    if not violations:
        click.echo(f"SUCC: {path}/pyproject.toml: no exact umbrella member pins")
        sys.exit(0)
    prefix = "ERRO" if strict else "WARN"
    for v in violations:
        click.echo(f"{prefix}: {path}/pyproject.toml: {v}", err=True)
    sys.exit(1 if strict else 0)


if __name__ == "__main__":
    cli()
