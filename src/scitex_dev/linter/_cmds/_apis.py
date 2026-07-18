"""``scitex-dev linter list-python-apis`` command.

Extracted from ``cli.py`` (512-line budget).
"""

from __future__ import annotations

import json
import sys

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(main_group):
    """Attach the ``list-python-apis`` command to ``main_group``."""

    @main_group.command(
        "list-python-apis",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="List the public Python API surface of scitex_linter.",
            examples=(
                Example("{prog} linter list-python-apis", "Names only."),
                Example(
                    "{prog} linter list-python-apis -vv",
                    "Signatures plus docstrings.",
                ),
                Example(
                    "{prog} linter list-python-apis --json",
                    "Machine-readable output.",
                ),
            ),
        ),
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    @click.option(
        "-v",
        "--verbose",
        count=True,
        default=0,
        help="Verbosity: -v signatures, -vv +docstrings, -vvv full.",
    )
    def list_python_apis(as_json, verbose):
        from .._cmd_api import _PUBLIC_API

        if as_json:
            data = [
                {"module": m, "kind": k, "name": n, "signature": s, "doc": d}
                for m, k, n, s, d in _PUBLIC_API
            ]
            click.echo(json.dumps(data, indent=2))
            return

        use_color = sys.stdout.isatty()
        cyan = "\033[96m" if use_color else ""
        green = "\033[92m" if use_color else ""
        yellow = "\033[93m" if use_color else ""
        blue = "\033[94m" if use_color else ""
        dim = "\033[2m" if use_color else ""
        reset = "\033[0m" if use_color else ""
        kind_color = {"F": green, "C": yellow, "V": blue}

        click.echo(f"API tree of scitex_linter ({len(_PUBLIC_API)} items):")
        click.echo("Legend: [M]=Module [C]=Class [F]=Function [V]=Variable")
        current_mod = None
        for mod, kind, name, sig, doc in _PUBLIC_API:
            if mod != current_mod:
                click.echo(f"{cyan}[M] {mod}{reset}")
                current_mod = mod
            kc = kind_color.get(kind, "")
            if verbose == 0:
                click.echo(f"  {kc}[{kind}]{reset} {name}")
            else:
                sep = "" if sig.startswith("(") else " "
                click.echo(f"  {kc}[{kind}]{reset} {name}{sep}{sig}")
                if verbose >= 2 and doc:
                    click.echo(f"       {dim}{doc}{reset}")

    return list_python_apis


# EOF
