"""CLI entry point for `scitex-dev linter` (Click-based, audit-compliant).

Canonical subcommands:
    scitex-dev linter validate-files <PATH> [--json] [--severity] [--category] [--no-color]
    scitex-dev linter format-files <PATH> [--check] [--diff] [--dry-run] [--yes]
    scitex-dev linter run-python <SCRIPT> [--strict] [-- script_args...]
    scitex-dev linter list-rules [--json] [--category] [--severity]      (built-in)
    scitex-dev linter list-rules-all [--json] [--category] [--severity]  (built-in + plugin)
    scitex-dev linter list-python-apis [-v|-vv|-vvv] [--json]
    scitex-dev linter mcp start [--dry-run] [--yes]
    scitex-dev linter mcp list-tools [-v|-vv|-vvv] [--json]
    scitex-dev linter mcp doctor
    scitex-dev linter mcp show-installation
    scitex-dev linter completion install [--shell bash|zsh] [--dry-run] [--yes]
    scitex-dev linter show-completion-status [--json]
    scitex-dev linter show-completion-bash
    scitex-dev linter show-completion-zsh

Deprecated aliases (still work, redirect to new names):
    check         -> validate-files
    check-files   -> validate-files
    format        -> format-files
    python        -> run-python
    rule          -> list-rules
    rules         -> list-rules-all
    api           -> list-python-apis
    mcp installation -> mcp show-installation
    completion status -> show-completion-status
    completion bash   -> show-completion-bash
    completion zsh    -> show-completion-zsh
"""

from __future__ import annotations

import json
import sys

import click

from . import __version__
from .._ecosystem.help_spec import CliHelp, Example, SpecGroup
from .rules import ALL_RULES

# =========================================================================
# Helpers
# =========================================================================


def _print_help_recursive(ctx: click.Context, _param, value):
    """Eager callback for --help-recursive."""
    if not value or ctx.resilient_parsing:
        return
    cmd = ctx.command
    click.echo(cmd.get_help(ctx))

    def walk(group, ancestry):
        if not isinstance(group, click.Group):
            return
        for name in sorted(group.commands):
            sub = group.commands[name]
            sub_ctx = click.Context(sub, info_name=name, parent=ctx)
            click.echo("\n---\n")
            click.echo(f"$ {' '.join(ancestry + [name])} --help\n")
            click.echo(sub.get_help(sub_ctx))
            walk(sub, ancestry + [name])

    walk(cmd, ["scitex-dev", "linter"])
    ctx.exit(0)


# =========================================================================
# Root
# =========================================================================


@click.group(
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=SpecGroup,
    command_categories=[
        ("Core", ["validate-files", "format-files", "lint-and-run", "sweep"]),
        ("Service", ["mcp"]),
        ("Introspection", ["list-rules", "list-rules-all", "list-python-apis"]),
        (
            "Shell",
            [
                "install-shell-completion",
                "print-shell-completion",
                "show-completion-status",
                "show-completion-bash",
                "show-completion-zsh",
            ],
        ),
    ],
    help_spec=CliHelp(
        summary="SciTeX Linter — enforce reproducible research patterns.",
        examples=(
            Example("{prog} linter validate-files src/", "Lint a source tree."),
            Example("{prog} linter list-rules --json", "Machine-readable rule list."),
            Example("{prog} linter mcp list-tools", "Show the MCP tool surface."),
        ),
        config_resolution=(
            "Highest -> lowest precedence:",
            "1. Explicit CLI flags",
            "2. ./pyproject.toml [tool.scitex_dev.linter] "
            "(legacy [tool.scitex-linter] still read)",
            "3. ./config.yaml (project-local)",
            "4. $SCITEX_DEV_LINTER_CONFIG (path to a YAML file)",
            "5. ~/.scitex/dev/linter/config.yaml (user-wide)",
            "6. Built-in defaults",
        ),
    ),
)
@click.version_option(__version__, "-V", "--version", prog_name="scitex-dev linter")
@click.option(
    "--help-recursive",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_help_recursive,
    help="Show help for the root command and every subcommand.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit machine-readable JSON output where supported.",
)
@click.pass_context
def main_group(ctx, as_json):
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =========================================================================
# validate-files (lives in ._cmd_check; registered here, re-exported for
# compat). Command renamed from `check-files` 2026-07-11 (§1f); the
# module stays `_cmd_check.py` — pure internal filename, not user-facing.
# =========================================================================

from ._cmd_check import _do_check  # noqa: E402,F401  back-compat re-export
from ._cmd_check import _collect_files  # noqa: E402,F401  back-compat re-export
from ._cmd_check import register as _register_validate_files  # noqa: E402

validate_files = _register_validate_files(main_group)

# Real (Click-registered) deprecated aliases, NOT just the `_rewrite_argv`
# shim below: `scitex-dev linter check-files ...` (the primary entry
# point, wired via `_cli/_root.py` attaching THIS `main_group` object
# directly) dispatches straight into Click's subcommand tree and never
# goes through this module's own `main()` / `_rewrite_argv` — that shim
# only fires for the secondary `python -m scitex_dev.linter` entry
# point. Without a real registered alias, the primary entry point would
# 404 on the old name the instant it stopped being canonical.
from .._ecosystem.click_compat import deprecated_alias  # noqa: E402

deprecated_alias(
    main_group,
    "check-files",
    target="validate-files",
    remove_in="0.32",
    phase="warn",
)
deprecated_alias(
    main_group,
    "check",
    target="validate-files",
    remove_in="0.32",
    phase="warn",
)


# =========================================================================
# format-files / lint-and-run / list-rules(-all) / list-python-apis
# (extracted to ._cmds; registered here, re-exported for compat)
# =========================================================================

from ._cmds._apis import register as _register_apis  # noqa: E402
from ._cmds._format import _do_format  # noqa: E402,F401  back-compat re-export
from ._cmds._format import register as _register_format  # noqa: E402
from ._cmds._rules import _do_list_rules  # noqa: E402,F401  back-compat re-export
from ._cmds._rules import register as _register_rules  # noqa: E402
from ._cmds._run import register as _register_run  # noqa: E402

format_files = _register_format(main_group)
run_python = _register_run(main_group)
list_rules_cmd, list_rules_all = _register_rules(main_group)
list_python_apis = _register_apis(main_group)



# =========================================================================
# mcp group + completion commands (extracted; registered here)
# =========================================================================

from ._cmd_mcp import register as _register_mcp  # noqa: E402
from ._cmd_completion_cmds import (  # noqa: E402
    register as _register_completion,
)

mcp_group = _register_mcp(main_group)
completion_group = _register_completion(main_group)


# =========================================================================
# §1a: install-shell-completion + print-shell-completion (canonical leaves)
# Registered alongside the legacy `completion install` / `show-completion-*`
# commands; the canonical leaves are the §1a-required entry points.
# =========================================================================
try:
    from scitex_dev._cli._completion import attach_shell_completion

    attach_shell_completion(main_group, prog_name="scitex-dev linter")
except ImportError:
    pass


# =========================================================================
# Backward-compat shim: translate deprecated argv names to new names
# =========================================================================

_TOP_RENAMES = {
    # §1f (2026-07-11): `check` is a non-canonical synonym for the
    # ecosystem-wide `validate` verb, so `check-files` was itself renamed
    # to `validate-files`. Both older spellings still rewrite straight to
    # the current canonical name (no double-hop through the retired
    # `check-files` name).
    "check": "validate-files",
    "check-files": "validate-files",
    "format": "format-files",
    "python": "lint-and-run",
    "run-python": "lint-and-run",
    "run-python-script": "lint-and-run",
    "rule": "list-rules",
    "rules": "list-rules-all",
    "api": "list-python-apis",
}

_MCP_RENAMES = {
    "installation": "show-installation",
}

_COMPLETION_RENAMES_TO_TOP = {
    # `completion <name>` -> top-level `show-completion-<name>`
    "status": "show-completion-status",
    "bash": "show-completion-bash",
    "zsh": "show-completion-zsh",
}


def _rewrite_argv(argv):
    """Translate deprecated subcommand names to canonical Click names.

    Preserves all flags and positional arguments verbatim.
    """
    if not argv:
        return argv

    # Find the first non-flag token (the subcommand)
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        i += 1
    if i >= len(argv):
        return argv

    sub = argv[i]
    if sub in _TOP_RENAMES:
        argv = argv[:i] + [_TOP_RENAMES[sub]] + argv[i + 1 :]
    elif sub == "mcp" and i + 1 < len(argv):
        nxt = argv[i + 1]
        if nxt in _MCP_RENAMES:
            argv = argv[: i + 1] + [_MCP_RENAMES[nxt]] + argv[i + 2 :]
    elif sub == "completion" and i + 1 < len(argv):
        nxt = argv[i + 1]
        if nxt in _COMPLETION_RENAMES_TO_TOP:
            argv = argv[:i] + [_COMPLETION_RENAMES_TO_TOP[nxt]] + argv[i + 2 :]
    return argv


def main(argv: list = None) -> int:
    """Entry point. Returns exit code (0 on success).

    Wraps Click so existing callers (and tests) that pass argv lists keep working.
    Translates deprecated subcommand names to canonical Click names.
    """
    raw = list(sys.argv[1:]) if argv is None else list(argv)
    raw = _rewrite_argv(raw)

    try:
        main_group.main(args=raw, prog_name="scitex-dev linter", standalone_mode=False)
        return 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return code
    except click.exceptions.UsageError as e:
        click.echo(f"Error: {e.format_message()}", err=True)
        return 2
    except click.exceptions.Abort:
        click.echo("Aborted.", err=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
