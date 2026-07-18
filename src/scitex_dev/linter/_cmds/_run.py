"""``scitex-dev linter lint-and-run`` command.

Extracted from ``cli.py`` (512-line budget).
"""

from __future__ import annotations

import sys

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(main_group):
    """Attach the ``lint-and-run`` command to ``main_group``."""

    @main_group.command(
        "lint-and-run",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Lint then execute a Python script.",
            description="Use -- to separate script arguments from linter flags.",
            examples=(
                Example(
                    "{prog} linter lint-and-run my_script.py", "Lint, then run."
                ),
                Example(
                    "{prog} linter lint-and-run my_script.py --strict",
                    "Abort on lint errors.",
                ),
                Example(
                    "{prog} linter lint-and-run my_script.py -- --arg1 value",
                    "Pass arguments through to the script.",
                ),
            ),
        ),
    )
    @click.argument("script", type=click.Path())
    @click.option("--strict", is_flag=True, default=False, help="Abort on lint errors.")
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    @click.argument("script_args", nargs=-1, type=click.UNPROCESSED)
    def run_python(script, strict, as_json, script_args):
        from ..runner import run_script

        sys.exit(run_script(script, strict=strict, script_args=list(script_args)))

    return run_python


# EOF
