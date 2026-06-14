"""``hooks list`` and ``hooks print-path`` subcommands (read-only)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from ._registry import KNOWN_HOOKS, list_one


def _hooks_path_status(project: Path) -> tuple[str, str]:
    """Inspect ``core.hooksPath`` on ``project``. Returns (status, value).

    Status words used by ``hooks list`` so the pre-push gate's
    activation state surfaces alongside the symlink-presence rows:

    ``wired``           — ``core.hooksPath = .githooks`` (the gate fires).
    ``unset``           — git default; bundled symlinks in ``.githooks/``
                          are NO-OPs until ``enable-pre-push`` wires it.
    ``points-elsewhere`` — operator chose a non-`.githooks` dir; the
                           bundled symlinks at ``.githooks/`` won't fire.
    ``no-git``          — git binary not on PATH or ``project`` not a
                           repo; can't determine status.
    """
    try:
        rc = subprocess.run(
            ["git", "-C", str(project), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return "no-git", ""
    value = rc.stdout.strip()
    if not value:
        return "unset", ""
    if value == ".githooks":
        return "wired", value
    return "points-elsewhere", value


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
        # Probe `core.hooksPath` so the operator sees whether the bundled
        # gate would actually fire (a symlink at .githooks/pre-push is a
        # no-op unless core.hooksPath points at .githooks). Surfacing
        # this in `hooks list` makes the "half-installed gate" state
        # impossible to miss — the symbol changes from `ok` to `wired`
        # only when both halves are in place.
        hp_status, hp_value = _hooks_path_status(project)
        if as_json:
            click.echo(
                _json.dumps(
                    {
                        "hooks_path": {"status": hp_status, "value": hp_value},
                        "hooks": [
                            {
                                "name": n,
                                "status": s,
                                "source": src,
                                "target": tgt,
                            }
                            for n, s, src, tgt in rows
                        ],
                    },
                    indent=2,
                )
            )
            return
        # Print the hooksPath status header first so the symlink rows
        # below have context.
        hp_symbol = {
            "wired": click.style("wired           ", fg="green"),
            "unset": click.style("unset           ", fg="white"),
            "points-elsewhere": click.style("points-elsewhere", fg="yellow"),
            "no-git": click.style("no-git          ", fg="red"),
        }[hp_status]
        hp_suffix = f" → {hp_value!r}" if hp_value else ""
        click.echo(f"{hp_symbol}  core.hooksPath{hp_suffix}")
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
