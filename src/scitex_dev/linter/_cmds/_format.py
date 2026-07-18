"""``scitex-dev linter format-files`` command.

Extracted from ``cli.py`` (512-line budget). ``_do_format`` is
re-exported from ``cli`` for back-compat with callers/tests that import
it from there.
"""

from __future__ import annotations

import sys

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def _do_format(path, check, diff, dry_run, as_json):
    from .._format_runner import run as _format_run

    return _format_run(path, check=check, diff=diff, dry_run=dry_run, as_json=as_json)


def register(main_group):
    """Attach the ``format-files`` command to ``main_group``."""

    @main_group.command(
        "format-files",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Auto-fix SciTeX pattern issues in Python files.",
            examples=(
                Example("{prog} linter format-files src/", "Fix a whole tree."),
                Example(
                    "{prog} linter format-files my_script.py --diff",
                    "Show a diff of the changes.",
                ),
                Example(
                    "{prog} linter format-files src/ --check",
                    "Exit 1 if changes are needed; write nothing.",
                ),
            ),
        ),
    )
    @click.argument("path", type=click.Path())
    @click.option(
        "--check",
        is_flag=True,
        default=False,
        help="Check if changes needed without writing (exit 1 if changes needed).",
    )
    @click.option("--diff", is_flag=True, default=False, help="Show diff of changes.")
    @click.option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Show what would be fixed without writing.",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        default=False,
        help="Skip confirmation (no-op; format is non-destructive on --check/--dry-run).",
    )
    @click.option(
        "--json", "as_json", is_flag=True, default=False, help="Output as JSON."
    )
    def format_files(path, check, diff, dry_run, yes, as_json):
        sys.exit(_do_format(path, check, diff, dry_run, as_json))

    return format_files


# EOF
