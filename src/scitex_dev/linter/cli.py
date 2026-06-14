"""CLI entry point for `scitex-dev linter` (Click-based, audit-compliant).

Canonical subcommands:
    scitex-dev linter check-files <PATH> [--json] [--severity] [--category] [--no-color]
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
    check         -> check-files
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
from pathlib import Path

import click

from . import __version__
from .checker import lint_file
from .config import load_config
from .formatter import format_issue, format_summary, to_json
from .rules import ALL_RULES, SEVERITY_ORDER

# =========================================================================
# Helpers
# =========================================================================


def _collect_files(path: Path, recursive: bool = True, config=None) -> list:
    """Collect Python and Jupyter notebook files from a path."""
    from ._collect import collect_files

    return collect_files(path, recursive=recursive, config=config)


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
    """SciTeX Linter — enforce reproducible research patterns.

    \b
    Configuration precedence (highest -> lowest):
      1. Explicit CLI flags
      2. ./pyproject.toml [tool.scitex_dev.linter]  (legacy [tool.scitex-linter] still read)
      3. ./config.yaml (project-local)
      4. $SCITEX_DEV_LINTER_CONFIG (path to a YAML file)
      5. ~/.scitex/dev/linter/config.yaml (user-wide)
      6. Built-in defaults

    \b
    Example:
        $ scitex-dev linter check-files src/
        $ scitex-dev linter list-rules --json
        $ scitex-dev linter mcp list-tools
    """
    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# =========================================================================
# check-files
# =========================================================================


def _do_check(path, as_json, no_color, severity, category):
    config = load_config(path)
    use_color = not no_color and sys.stdout.isatty()
    min_sev = SEVERITY_ORDER[severity]
    categories = set(category.split(",")) if category else None

    target = Path(path)
    if not target.exists():
        click.echo(f"Error: {path} not found", err=True)
        return 2

    files = _collect_files(target, config=config)
    if not files:
        click.echo(f"No Python files found in {path}", err=True)
        return 0

    all_results = {}
    for f in files:
        issues = lint_file(str(f), config=config)
        issues = [
            i
            for i in issues
            if SEVERITY_ORDER[i.rule.severity] >= min_sev
            and (categories is None or i.rule.category in categories)
        ]
        if issues:
            all_results[str(f)] = issues

    if as_json:
        combined = {fp: to_json(issues, fp) for fp, issues in all_results.items()}
        click.echo(json.dumps(combined, indent=2))
        has_errors = any(
            any(i.rule.severity == "error" for i in issues)
            for issues in all_results.values()
        )
        return 2 if has_errors else (1 if all_results else 0)

    if not all_results:
        msg = "All files clean"
        if use_color:
            click.echo(f"\033[92m{msg}\033[0m")
        else:
            click.echo(msg)
        return 0

    has_errors = False
    for filepath, issues in all_results.items():
        for issue in issues:
            click.echo(format_issue(issue, filepath, color=use_color))
            if issue.rule.severity == "error":
                has_errors = True
        click.echo(format_summary(issues, filepath, color=use_color))
        click.echo()
    return 2 if has_errors else 1


@main_group.command("check-files")
@click.argument("path", type=click.Path())
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option("--no-color", is_flag=True, default=False, help="Disable colored output.")
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default="info",
    help="Minimum severity to report (default: info).",
)
@click.option(
    "--category",
    default=None,
    help="Filter by category (comma-separated: structure,import,io,plot,stats).",
)
def check_files(path, as_json, no_color, severity, category):
    """Check Python files for SciTeX pattern compliance.

    \b
    Example:
        $ scitex-dev linter check-files src/
        $ scitex-dev linter check-files my_script.py --json
        $ scitex-dev linter check-files src/ --severity error --no-color
    """
    sys.exit(_do_check(path, as_json, no_color, severity, category))


# =========================================================================
# format-files
# =========================================================================


def _do_format(path, check, diff, dry_run, as_json):
    from ._format_runner import run as _format_run

    return _format_run(path, check=check, diff=diff, dry_run=dry_run, as_json=as_json)


@main_group.command("format-files")
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
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def format_files(path, check, diff, dry_run, yes, as_json):
    """Auto-fix SciTeX pattern issues in Python files.

    \b
    Example:
        $ scitex-dev linter format-files src/
        $ scitex-dev linter format-files my_script.py --diff
        $ scitex-dev linter format-files src/ --check
    """
    sys.exit(_do_format(path, check, diff, dry_run, as_json))


# =========================================================================
# run-python
# =========================================================================


@main_group.command("lint-and-run")
@click.argument("script", type=click.Path())
@click.option("--strict", is_flag=True, default=False, help="Abort on lint errors.")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.argument("script_args", nargs=-1, type=click.UNPROCESSED)
def run_python(script, strict, as_json, script_args):
    """Lint then execute a Python script.

    Use -- to separate script arguments from linter flags.

    \b
    Example:
        $ scitex-dev linter run-python my_script.py
        $ scitex-dev linter run-python my_script.py --strict
        $ scitex-dev linter run-python my_script.py -- --arg1 value
    """
    from .runner import run_script

    sys.exit(run_script(script, strict=strict, script_args=list(script_args)))


# =========================================================================
# list-rules / list-rules-all
# =========================================================================


def _do_list_rules(rules_list, as_json):
    if as_json:
        data = [
            {
                "id": r.id,
                "severity": r.severity,
                "category": r.category,
                "message": r.message,
                "suggestion": r.suggestion,
            }
            for r in rules_list
        ]
        click.echo(json.dumps(data, indent=2))
        return
    use_color = sys.stdout.isatty()
    sev_color = {"error": "\033[91m", "warning": "\033[93m", "info": "\033[94m"}
    reset = "\033[0m"
    for r in rules_list:
        if use_color:
            c = sev_color.get(r.severity, "")
            click.echo(f"  {c}{r.id}{reset}  [{r.severity}]  {r.message}")
        else:
            click.echo(f"  {r.id}  [{r.severity}]  {r.message}")
    click.echo(f"\n  {len(rules_list)} rules")


@main_group.command("list-rules")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "--category",
    default=None,
    help="Filter by category (comma-separated: structure,import,io,plot,stats).",
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default=None,
    help="Filter by severity.",
)
def list_rules_cmd(as_json, category, severity):
    """List all built-in SciTeX lint rules.

    \b
    Example:
        $ scitex-dev linter list-rules
        $ scitex-dev linter list-rules --json
        $ scitex-dev linter list-rules --category structure --severity error
    """
    categories = set(category.split(",")) if category else None
    rules_list = list(ALL_RULES.values())
    if categories:
        rules_list = [r for r in rules_list if r.category in categories]
    if severity:
        rules_list = [r for r in rules_list if r.severity == severity]
    _do_list_rules(rules_list, as_json)


@main_group.command("list-rules-all")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "--category", default=None, help="Filter by category (e.g. io, plot, structure)."
)
@click.option(
    "--severity",
    type=click.Choice(["error", "warning", "info"]),
    default=None,
    help="Filter by severity.",
)
def list_rules_all(as_json, category, severity):
    """List all SciTeX lint rules, including plugin-contributed rules.

    \b
    Example:
        $ scitex-dev linter list-rules-all
        $ scitex-dev linter list-rules-all --category io
    """
    from . import list_rules as _lr

    rules_list = _lr(category=category)
    if severity:
        rules_list = [r for r in rules_list if r.severity == severity]
    _do_list_rules(rules_list, as_json)


# =========================================================================
# list-python-apis
# =========================================================================


@main_group.command("list-python-apis")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "-v",
    "--verbose",
    count=True,
    default=0,
    help="Verbosity: -v signatures, -vv +docstrings, -vvv full.",
)
def list_python_apis(as_json, verbose):
    """List the public Python API surface of scitex_linter.

    \b
    Example:
        $ scitex-dev linter list-python-apis
        $ scitex-dev linter list-python-apis -vv
        $ scitex-dev linter list-python-apis --json
    """
    from ._cmd_api import _PUBLIC_API

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


# =========================================================================
# mcp group
# =========================================================================


@main_group.group("mcp", invoke_without_command=True)
@click.pass_context
def mcp_group(ctx):
    """MCP (Model Context Protocol) server management.

    \b
    Example:
        $ scitex-dev linter mcp start
        $ scitex-dev linter mcp list-tools
        $ scitex-dev linter mcp doctor
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@mcp_group.command("start")
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse"]),
    default="stdio",
    help="Transport mode (default: stdio).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would happen without starting the server.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation prompts.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def mcp_start(transport, dry_run, yes, as_json):
    """Start the MCP server.

    \b
    Example:
        $ scitex-dev linter mcp start
        $ scitex-dev linter mcp start --transport sse
        $ scitex-dev linter mcp start --dry-run
    """
    if dry_run:
        click.echo(f"Would start MCP server (transport={transport}).")
        return
    try:
        from ._server import run_server

        run_server(transport=transport)
    except ImportError:
        click.echo(
            "fastmcp is required for MCP server. "
            "Install with: pip install 'scitex-dev[mcp]'",
            err=True,
        )
        sys.exit(1)


@mcp_group.command("list-tools")
@click.option(
    "-v",
    "--verbose",
    count=True,
    default=0,
    help="Verbosity: -v sig, -vv +desc, -vvv full.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def mcp_list_tools(verbose, as_json):
    """List available MCP tools exposed by `scitex-dev linter`.

    \b
    Example:
        $ scitex-dev linter mcp list-tools
        $ scitex-dev linter mcp list-tools -vv
        $ scitex-dev linter mcp list-tools --json
    """
    _KNOWN_TOOLS = ["linter_check", "linter_check_source", "linter_list_rules"]
    tools = []
    try:
        from ._server import mcp as mcp_server
        from .._ecosystem._mcp import get_tools_sync

        tools = list(get_tools_sync(mcp_server).values())
    except Exception:
        pass

    if as_json:
        if not tools:
            click.echo(json.dumps({"tools": _KNOWN_TOOLS}, indent=2))
        else:
            click.echo(
                json.dumps(
                    {"tools": [t.name for t in sorted(tools, key=lambda t: t.name)]},
                    indent=2,
                )
            )
        return

    if not tools:
        click.echo(f"SciTeX Linter MCP\nTools: {len(_KNOWN_TOOLS)}\n")
        for n in _KNOWN_TOOLS:
            click.echo(f"  {n}")
        return
    C = sys.stdout.isatty()
    g, w, cy, y, dm, r = (
        ("\033[92m", "\033[1;37m", "\033[96m", "\033[93m", "\033[2m", "\033[0m")
        if C
        else ("",) * 6
    )
    click.echo(f"{cy}SciTeX Linter MCP{r}\nTools: {len(tools)}\n")
    for t in sorted(tools, key=lambda t: t.name):
        if verbose == 0:
            click.echo(f"  {t.name}")
        else:
            ps = []
            params = t.parameters or {}
            for p, i in params.get("properties", {}).items():
                pt = i.get("type", "any")
                if p in params.get("required", []):
                    ps.append(f"{w}{p}{r}: {cy}{pt}{r}")
                else:
                    d = (
                        repr(i.get("default"))
                        if i.get("default") is not None
                        else "None"
                    )
                    ps.append(f"{w}{p}{r}: {cy}{pt}{r} = {y}{d}{r}")
            click.echo(f"  {g}{t.name}{r}({', '.join(ps)})")
            if verbose >= 2 and t.description:
                desc = t.description.split("\n")[0]
                click.echo(f"       {dm}{desc}{r}")
                if verbose >= 3:
                    for line in t.description.strip().split("\n")[1:]:
                        click.echo(f"       {dm}{line}{r}")
                click.echo()


@mcp_group.command("doctor")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def mcp_doctor(as_json):
    """Check MCP server health.

    \b
    Example:
        $ scitex-dev linter mcp doctor
    """
    import shutil

    click.echo(f"scitex-dev linter {__version__}\n")
    click.echo("Health Check")
    click.echo("=" * 40)

    checks = []
    try:
        import fastmcp

        checks.append(("fastmcp", True, fastmcp.__version__))
    except ImportError:
        checks.append(("fastmcp", False, "not installed"))
    try:
        from ._mcp.tools import register_all_tools  # noqa: F401

        checks.append(("MCP tools", True, "3 tools"))
    except Exception as e:
        checks.append(("MCP tools", False, str(e)))
    cli_path = shutil.which("scitex-dev")
    checks.append(("CLI", bool(cli_path), cli_path if cli_path else "not in PATH"))
    checks.append(("Rules", True, f"{len(ALL_RULES)} rules"))

    all_ok = True
    for name, ok, info in checks:
        status = "\u2713" if ok else "\u2717"
        if not ok:
            all_ok = False
        click.echo(f"  {status} {name}: {info}")
    click.echo()
    if all_ok:
        click.echo("All checks passed!")
    else:
        click.echo("Some checks failed. Run 'pip install scitex-dev[mcp]' to fix.")
    sys.exit(0 if all_ok else 1)


@mcp_group.command(
    "show-installation",
    hidden=True,
    context_settings={"ignore_unknown_options": True},
)
@click.pass_context
def mcp_show_installation_deprecated(ctx):
    """(deprecated) Renamed to `install`."""
    click.echo(
        "error: `scitex-dev linter mcp show-installation` was renamed to "
        "`scitex-dev linter mcp install`.\n"
        "Re-run with: scitex-dev linter mcp install",
        err=True,
    )
    ctx.exit(2)


@mcp_group.command("install")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Accepted for §2; this verb is informational, never mutates state.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    help="Accepted for §2; this verb is informational, never mutates state.",
)
def mcp_install(as_json, dry_run, yes):
    """Show Claude Desktop MCP configuration snippet.

    \b
    Example:
        $ scitex-dev linter mcp install
    """
    del dry_run, yes  # audit §2 — no-op flags
    import shutil

    click.echo(f"scitex-dev linter {__version__}\n")
    click.echo("Add this to your Claude Desktop config file:\n")
    click.echo(
        "  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json"
    )
    click.echo("  Linux: ~/.config/Claude/claude_desktop_config.json\n")
    cli_path = shutil.which("scitex-dev")
    if cli_path:
        click.echo(f"Your installation path: {cli_path}\n")
    config = (
        "{\n"
        '  "mcpServers": {\n'
        '    "scitex-dev-linter": {\n'
        f'      "command": "{cli_path or "scitex-dev"}",\n'
        '      "args": ["linter", "mcp", "start"]\n'
        "    }\n"
        "  }\n"
        "}"
    )
    click.echo(config)


# =========================================================================
# completion group
# =========================================================================


@main_group.group("completion")
def completion_group():
    """Shell tab-completion management.

    \b
    Example:
        $ scitex-dev linter completion install --shell bash
        $ scitex-dev linter show-completion-status
    """


def _completion_script(shell):
    from ._cmd_completion import _generate_completion_script

    return _generate_completion_script(shell)


@completion_group.command("install")
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh"]),
    default=None,
    help="Shell type (auto-detected if not provided).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be installed without writing.",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip confirmation.",
)
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def completion_install(shell, dry_run, yes, as_json):
    """Install completion to shell RC file.

    \b
    Example:
        $ scitex-dev linter completion install
        $ scitex-dev linter completion install --shell zsh
        $ scitex-dev linter completion install --dry-run
    """
    import os

    if not shell:
        shell_env = os.environ.get("SHELL", "")
        shell = "zsh" if "zsh" in shell_env else "bash"

    script = _completion_script(shell)
    if not script:
        click.echo(f"Unsupported shell: {shell}", err=True)
        sys.exit(1)

    rc_file = os.path.expanduser("~/.bashrc" if shell == "bash" else "~/.zshrc")

    if os.path.exists(rc_file):
        with open(rc_file) as f:
            if "scitex-dev linter tab completion" in f.read():
                click.echo(f"Completion already installed in {rc_file}")
                return

    if dry_run:
        click.echo(f"Would append completion script to {rc_file}")
        return

    if not yes:
        click.echo(
            f"Refusing to modify {rc_file} without --yes/-y.",
            err=True,
        )
        raise SystemExit(2)

    with open(rc_file, "a") as f:
        f.write(f"\n{script}\n")
    click.echo(f"Completion installed in {rc_file}")
    click.echo(f"Reload with: source {rc_file}")


@main_group.command("show-completion-status")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def show_completion_status(as_json):
    """Show shell completion installation status.

    \b
    Example:
        $ scitex-dev linter show-completion-status
        $ scitex-dev linter show-completion-status --json
    """
    import os

    shell_env = os.environ.get("SHELL", "")
    shell = "zsh" if "zsh" in shell_env else "bash"
    rc_file = os.path.expanduser("~/.bashrc" if shell == "bash" else "~/.zshrc")
    installed = False
    if os.path.exists(rc_file):
        with open(rc_file) as f:
            if "scitex-dev linter tab completion" in f.read():
                installed = True

    if as_json:
        click.echo(
            json.dumps(
                {"shell": shell, "rc_file": rc_file, "installed": installed},
                indent=2,
            )
        )
        return

    click.echo(f"Shell:  {shell}")
    click.echo(f"RC:     {rc_file}")
    click.echo(f"Status: {'installed' if installed else 'not installed'}")
    if not installed:
        click.echo("\nInstall with: scitex-dev linter completion install")


@main_group.command("show-completion-bash")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def show_completion_bash(as_json):
    """Print the bash completion script to stdout.

    \b
    Example:
        $ scitex-dev linter show-completion-bash > /etc/bash_completion.d/scitex-dev-linter
    """
    script = _completion_script("bash")
    if as_json:
        click.echo(json.dumps({"shell": "bash", "script": script}, indent=2))
    else:
        click.echo(script)


@main_group.command("show-completion-zsh")
@click.option("--json", "as_json", is_flag=True, default=False, help="Output as JSON.")
def show_completion_zsh(as_json):
    """Print the zsh completion script to stdout.

    \b
    Example:
        $ scitex-dev linter show-completion-zsh > ~/.zsh/completions/_scitex-dev-linter
    """
    script = _completion_script("zsh")
    if as_json:
        click.echo(json.dumps({"shell": "zsh", "script": script}, indent=2))
    else:
        click.echo(script)


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
    "check": "check-files",
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
