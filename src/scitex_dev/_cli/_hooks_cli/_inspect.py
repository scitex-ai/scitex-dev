"""``hooks list`` and ``hooks show-path`` leaves (+ ``print-path`` alias)."""

from __future__ import annotations

from pathlib import Path

import click

from ..._ecosystem.click_compat import deprecated_alias
from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand
from ._registry import KNOWN_HOOKS, _list_one


def register_inspect(hooks_group) -> None:
    """Attach the ``list`` and ``show-path`` leaves to ``hooks_group``."""

    @hooks_group.command(
        "list",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Show the install status of each hook.",
            description=(
                "Reports which hooks are installed and whether they "
                "point at the canonical source: ok, drift, stale, or "
                "missing.",
            ),
            examples=(
                Example(
                    "{prog} hooks list --target ~/proj/my-research",
                    "ok run_lint -> bundled canonical.",
                ),
            ),
        ),
    )
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
        import json as _json

        project = Path(target)
        rows = []
        for name in sorted(KNOWN_HOOKS):
            source, deploy_rel = KNOWN_HOOKS[name]
            status = _list_one(name, source, deploy_rel, project)
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
    #
    # Renamed AGAIN (2026-07-11, §1f): `print` is a non-canonical synonym
    # for the doctrine's one show-verb, `show` (cf. `cat`/`display`/`view`
    # → `show`). `print-path` stays registered as a warn-phase deprecated
    # alias below so existing `entry: bash $(scitex-dev hooks print-path
    # ...)` lines in pre-commit configs keep working.
    @hooks_group.command(
        "show-path",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Print the bundled hook script's absolute filesystem path.",
            description=(
                "Useful in shell scripts, e.g. to symlink the canonical "
                "hook manually instead of via `hooks install`.",
            ),
            examples=(
                Example(
                    "{prog} hooks show-path run_lint",
                    "/.../site-packages/scitex_dev/_hooks/run_lint.sh",
                ),
                Example(
                    '''ln -s "$({prog} hooks show-path run_lint)" docs/to_claude/hooks/post-tool-use/run_lint.sh''',
                    "Symlink it by hand.",
                ),
            ),
        ),
    )
    @click.argument("name", type=click.Choice(sorted(KNOWN_HOOKS), case_sensitive=False))
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        help=(
            "Emit {\"name\": ..., \"path\": ...} instead of the bare path. "
            "Default output stays a bare path on purpose — it's designed "
            "for direct command substitution, e.g. `ln -s \"$(... hooks "
            "show-path run_lint)\" ...`; --json is for scripted/programmatic "
            "callers that want structure (audit-cli §2)."
        ),
    )
    def hooks_show_path(name, as_json):
        source, _ = KNOWN_HOOKS[name]
        if as_json:
            import json as _json

            click.echo(_json.dumps({"name": name, "path": source}))
            return
        click.echo(source)

    deprecated_alias(
        hooks_group,
        "print-path",
        target="show-path",
        remove_in="0.32",
        phase="warn",
    )


__all__ = ["register_inspect"]
