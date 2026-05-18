"""Audit umbrella `scitex` pyproject.toml pins against PyPI latest.

Enforces the doctrine that the umbrella package pins every leaf at
``==<latest released version>``. Drift would mean the umbrella ships
referencing leaves that are behind their latest release — defeating
the point of release-tag-driven `git push origin v*` automation.

Run via:

    scitex-dev audit-umbrella-pins [PATH]

PATH defaults to the cwd. Exits 1 on any drift so CI fails loudly.
Network access required — queries https://pypi.org/pypi/<pkg>/json.

The audit only fires on the umbrella package (pyproject.toml `name =
"scitex"`); on any other package it exits 0 silently so it's safe to
wire into a shared CI matrix step.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

import click

UMBRELLA_NAME = "scitex"
# Match any of: scitex-X, figrecipe, newb, socialia (the publishable
# ecosystem leaves). Optional extras spec, then ==pin. Anything looser
# than `==` is also flagged so drift can't sneak in via `>=`.
_PIN_LINE_RE = re.compile(
    r'"(scitex-[a-z0-9-]+|figrecipe|newb|socialia)(\[[^\]]*\])?'
    r"(==|>=|~=|<=|<|>|!=)?"
    r'([0-9][0-9A-Za-z.\-]*)?"'
)
_NAME_RE = re.compile(r'^\s*name\s*=\s*"([^"]+)"', re.MULTILINE)


def _pypi_latest(pkg: str, timeout: float = 10.0) -> Optional[str]:
    url = f"https://pypi.org/pypi/{pkg}/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.load(resp)
        return data.get("info", {}).get("version")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return None


def audit_umbrella_pins(repo: Path) -> list[str]:
    """Return a list of violation strings. Empty list = clean."""
    pyproject = repo / "pyproject.toml"
    if not pyproject.is_file():
        return []
    txt = pyproject.read_text(errors="ignore")
    name_match = _NAME_RE.search(txt)
    if not name_match or name_match.group(1).strip() != UMBRELLA_NAME:
        return []  # only audit the umbrella

    seen: set[str] = set()
    violations: list[str] = []
    for match in _PIN_LINE_RE.finditer(txt):
        pkg = match.group(1)
        extras = match.group(2) or ""
        op = match.group(3) or ""
        ver = match.group(4) or ""
        key = pkg + extras
        if key in seen:
            continue
        seen.add(key)

        if op != "==" or not ver:
            violations.append(
                f"PS-170: {pkg}{extras} declared as {op!r}{ver!r} — "
                f"umbrella must pin with `=={'{latest}'}` so a release "
                f"snapshot is reproducible."
            )
            continue

        latest = _pypi_latest(pkg)
        if latest is None:
            # PyPI query failed — don't block CI on transient network,
            # but flag as warning. Caller decides whether to fail.
            violations.append(
                f"PS-170W: could not resolve PyPI latest for {pkg!r} "
                f"(network/timeout). Pin declared as =={ver}."
            )
            continue
        if ver != latest:
            violations.append(
                f"PS-170: {pkg}{extras}=={ver} but PyPI latest is "
                f"{latest}. Bump the umbrella pin."
            )

    return violations


@click.command("audit-umbrella-pins")
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd,
)
@click.option(
    "--allow-network-error",
    is_flag=True,
    help="Treat PyPI lookup failures as warnings, not errors (exit 0).",
)
def cli(path: Path, allow_network_error: bool) -> None:
    """Audit umbrella pin freshness vs PyPI latest."""
    violations = audit_umbrella_pins(path)
    if not violations:
        click.echo(f"SUCC: {path}/pyproject.toml: all umbrella pins fresh")
        sys.exit(0)

    hard_violations = [v for v in violations if not v.startswith("PS-170W")]
    for v in violations:
        click.echo(f"ERRO: {path}/pyproject.toml: {v}", err=True)

    if hard_violations or not allow_network_error:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    cli()
