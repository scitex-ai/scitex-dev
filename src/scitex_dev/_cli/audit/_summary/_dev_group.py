"""§13 — package self-maintenance commands nest under a `dev` group.

Split out as its own sibling module (same rationale as `_gui_group.py`
and `_std_rules.py`'s own splits from the legacy-oversized `_audit.py`):
keeps each audit rule-family small and independently readable instead of
growing one file past the repo's own 512-line limit.

Doctrine: ``_skills/general/03_interface/02_cli/20_dev-commands.md``.
Every self-maintenance verb a package ships — daemon/cron/systemd/hooks/
skills/shell — mounts under ONE group named `dev`, as
`<pkg> dev {daemon,cron,systemd,hooks,skills,shell}`, never at the CLI
top level. This is the enforcement half of an operator directive: a
package's user-facing surface is its domain verbs; its self-maintenance
plumbing belongs under `dev` so `<pkg> --help` reads as the tool, not
the tool's own housekeeping.
"""

from __future__ import annotations

import click

# The operator's canonical 6 self-maintenance verbs. Chosen because none
# is plausibly a package's DOMAIN verb (unlike image/ci/pytest/…), so
# flagging them at top level yields near-zero false positives.
#
# The broader package-maintenance set (image/installation/worktree/ci/
# pytest/provenance/list-python-apis) is a deliberate FUTURE extension,
# left OUT of v1: for some packages image/ci is genuinely a domain verb
# (a container tool's `image`, a CI tool's `ci`), so folding it in now
# would false-flag them. Start with the unambiguous 6; widen later once
# per-package allowlists exist.
DEV_SUBCOMMAND_NAMES = frozenset(
    {"daemon", "cron", "systemd", "hooks", "skills", "shell"}
)

__all__ = ["DEV_SUBCOMMAND_NAMES", "check_dev_command_group"]


def check_dev_command_group(
    root: click.BaseCommand, package: str, out: list
) -> None:
    """§13 — self-maintenance commands must nest under a `dev` group.

    Walks the whole command tree (hidden leaves included), tracking
    whether the current node sits under a `dev` ancestor group. A command
    whose name is one of ``DEV_SUBCOMMAND_NAMES`` and is NOT nested under
    a `dev` group is flagged — REPORTING-ONLY, no runtime behavior
    changes.

    Unlike §12 (gui), this rule enforces NESTING only: it does not
    require any fixed verb set to exist inside `dev`.

    ESCAPE HATCH (mirrors §12): a flagged command that is already a
    properly-deprecated Phase W/E alias — ``hidden`` AND carrying
    ``_deprecated_alias`` metadata (set by
    ``scitex_dev.ecosystem.deprecated_alias``) — is NOT flagged. A
    package that has already migrated `<pkg> cron` to a warn-forward
    alias for `<pkg> dev cron` must not be re-flagged here.

    Walks hidden commands too (unlike the main `_walk` §1-family checks)
    because recognizing an already-migrated Phase W/E alias requires
    inspecting hidden leaves — the same reason
    `check_deprecated_alias_metadata` and `check_gui_command_group` run
    their own walkers.
    """
    from ._audit import Violation

    if not isinstance(root, click.Group):
        return

    def _visit(
        cmd: click.BaseCommand, path: list[str], under_dev: bool
    ) -> None:
        name = path[-1]
        name_lc = name.lower()
        full = " ".join([package, *path])
        is_group = isinstance(cmd, click.Group)
        hidden = bool(getattr(cmd, "hidden", False))

        if name_lc in DEV_SUBCOMMAND_NAMES and not under_dev:
            meta = getattr(cmd, "_deprecated_alias", None)
            already_migrated = hidden and meta is not None
            if not already_migrated:
                out.append(
                    Violation(
                        full,
                        "§13",
                        f"self-maintenance command {name!r} at top level — "
                        f"nest under the `dev` group as `{package} dev "
                        f"{name}` (operator directive; doctrine "
                        f"20_dev-commands.md). Either move it under a `dev` "
                        f"group, or register a Phase W/E "
                        f"scitex_dev.ecosystem.deprecated_alias() forwarding "
                        f"to `dev {name}`.",
                    )
                )

        if is_group:
            child_under_dev = under_dev or name_lc == "dev"
            for sub_name, sub in cmd.commands.items():
                _visit(sub, path + [sub_name], child_under_dev)

    for top_name, top_cmd in root.commands.items():
        _visit(top_cmd, [top_name], False)


# EOF
