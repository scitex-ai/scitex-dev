"""``hooks list`` and ``hooks print-path`` subcommands (read-only)."""

from __future__ import annotations

from pathlib import Path

import click

from ._registry import KNOWN_HOOKS, list_one


def register(hooks_group) -> None:
    """Attach the ``list`` and ``print-path`` leaves to ``hooks_group``."""

    @hooks_group.command("list", short_help="Show the install status of each hook.")
    @click.option(
        "--target",
        "target",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, exists=True, resolve_path=True),
        help="Project root to inspect.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help=(
            "Emit machine-readable JSON instead of the coloured table. "
            "audit-cli §2 — every read verb must expose --json."
        ),
    )
    def hooks_list(target, as_json):
        """Report which hooks are installed and whether they point at
        the canonical source.

        \b
        Example:
            $ scitex-dev hooks list --target ~/proj/my-research
            ok       run_lint  → bundled canonical
            missing  …
        """
        import json as _json

        project = Path(target)
        rows = []
        for name in sorted(KNOWN_HOOKS):
            source, deploy_rel = KNOWN_HOOKS[name]
            status = list_one(name, source, deploy_rel, project)
            rows.append((name, status, source, str(project / deploy_rel)))
        if as_json:
            click.echo(
                _json.dumps(
                    [
                        {
                            "name": n,
                            "status": s,
                            "source": src,
                            "target": tgt,
                        }
                        for n, s, src, tgt in rows
                    ],
                    indent=2,
                )
            )
            return
        for name, status, _source, target_path in rows:
            symbol = {
                "ok": click.style("ok      ", fg="green"),
                "drift": click.style("drift   ", fg="yellow"),
                "stale": click.style("stale   ", fg="red"),
                "missing": click.style("missing ", fg="white"),
            }[status]
            click.echo(f"{symbol}  {name}  →  {target_path}")

    # Renamed `path` → `print-path` per audit-cli §1: a bare noun-typed
    # leaf at the verb position is forbidden (the auditor reads `path`
    # as a noun, not an action). `print-path` is the compound-leaf form
    # the catalog recommends for a one-off read action.
    @hooks_group.command(
        "print-path",
        short_help="Print the absolute path of a bundled hook script.",
        epilog=(
            "Example:\n"
            "  $ scitex-dev hooks print-path run_lint\n"
            "  /uvwork/venv-agent/lib/python3.12/site-packages/scitex_dev/_hooks/run_lint.sh\n"
            "\n"
            '  $ ln -s "$(scitex-dev hooks print-path run_lint)" \\\n'
            "      docs/to_claude/hooks/post-tool-use/run_lint.sh"
        ),
    )
    @click.argument(
        "name", type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False)
    )
    def hooks_print_path(name):
        """Print the bundled hook script's absolute filesystem path.

        \b
        Example:
            $ scitex-dev hooks print-path run_lint
            /uvwork/venv-agent/lib/python3.12/site-packages/scitex_dev/_hooks/run_lint.sh

        Useful in shell scripts:

        \b
            ln -s "$(scitex-dev hooks print-path run_lint)" \\
                docs/to_claude/hooks/post-tool-use/run_lint.sh
        """
        source, _ = KNOWN_HOOKS[name]
        click.echo(source)


__all__ = ["register"]
