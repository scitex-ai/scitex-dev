#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev registry-normalize`` — mechanical fix for PS-181 drift.

Mirrors ``_cli/_trace_env.py`` / ``_cli/_rename.py``: a thin
``register(main)`` entry point that wires the command to the top-level
click group; all real logic lives in the ``scitex_dev.registry_normalize``
engine package (shared with the PS-181 audit rule, so detection can never
drift between the two surfaces).

Safety, non-negotiable:

- Dry-run by default — pass ``--yes``/``-y`` to actually move files.
- Archive, never delete.
- A ``*.pid`` file naming a currently-alive process is SKIPPED, not moved.
- A ``*.sock`` file is ALWAYS skipped — liveness is not cheaply
  determinable for sockets; remove manually if you've confirmed it's
  stale.
- Exactly one ``<pkg>`` positional argument — no bulk "normalize
  everything" mode.
"""

from __future__ import annotations

import json
import sys

import click


def register(main: click.Group) -> None:
    """Attach the ``registry-normalize`` command to the top-level click group."""

    @main.command(
        "registry-normalize",
        epilog=(
            "Fixes PS-181 registry-layout drift for a SINGLE "
            "~/.scitex/<pkg>/ state directory.\n"
            "\n"
            "CAVEATS:\n"
            "  * dry-run by default — nothing is moved without --yes/-y.\n"
            "  * archive, never delete — every move has a destination.\n"
            "  * a *.pid file naming a LIVE process is skipped, not moved.\n"
            "  * *.sock files are ALWAYS skipped (liveness of a socket is "
            "not cheaply\n"
            "    determinable) — remove manually once you've confirmed "
            "it's stale.\n"
            "  * config-naming drift, __pycache__/, and venv-naming "
            "drift are reported\n"
            "    by `scitex-dev ecosystem audit-registry-layout` but NOT "
            "auto-moved here\n"
            "    (renaming a config file or a venv is not a safe "
            "mechanical move).\n"
            "\n"
            "Examples:\n"
            "  $ scitex-dev registry-normalize scitex-todo\n"
            "  $ scitex-dev registry-normalize scitex-todo --json\n"
            "  $ scitex-dev registry-normalize scitex-todo --yes"
        ),
    )
    @click.argument("pkg")
    @click.option(
        "--yes",
        "-y",
        "confirm",
        is_flag=True,
        help="Actually move files on disk. Without this flag, dry-run only.",
    )
    @click.option(
        "--scitex-dir",
        "scitex_dir_opt",
        type=click.Path(file_okay=False, dir_okay=True),
        default=None,
        help="Override $SCITEX_DIR (defaults to the resolved user root, ~/.scitex).",
    )
    @click.option("--json", "as_json", is_flag=True, help="Emit JSON output.")
    def _registry_normalize(pkg, confirm, scitex_dir_opt, as_json):
        """Fix ~/.scitex/<pkg>/ registry-layout drift (dry-run by default).

        \b
        Example:
            $ scitex-dev registry-normalize scitex-todo
            $ scitex-dev registry-normalize scitex-todo --yes
            $ scitex-dev registry-normalize scitex-todo --json
        """
        from pathlib import Path

        from ..registry_normalize import run_registry_normalize

        if scitex_dir_opt:
            scitex_dir = Path(scitex_dir_opt).expanduser()
        else:
            from scitex_config._ecosystem import local_state

            scitex_dir = local_state.user_root()

        report = run_registry_normalize(pkg, confirm=confirm, scitex_dir=scitex_dir)

        if as_json:
            click.echo(json.dumps(report.to_dict(), indent=2, default=str))
        elif report.error:
            click.echo(f"registry-normalize: {report.error}", err=True)
        else:
            mode = "APPLIED" if confirm else "DRY-RUN"
            click.echo(f"registry-normalize [{mode}] {report.pkg_dir}")
            if not report.moves:
                click.echo("  (no drift found — already conformant)")
            for m in report.moves:
                click.echo(f"  {m.detail}")

        sys.exit(2 if report.error else 0)


# EOF
