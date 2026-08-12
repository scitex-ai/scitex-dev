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

The six names, and the level each one sits at
---------------------------------------------
`DEV_SUBCOMMAND_NAMES` lists `daemon` beside `cron` and `systemd`, which
mixes two levels of abstraction: `daemon` names an INTENT (run
continuously), while `cron` and `systemd` name MECHANISMS (a crontab, a
systemd unit). `jobs/_kinds.py` diagnosed and fixed exactly this in the
job-kind enum one layer down, and the constitution states the rule —
"Name the INTENT, not the MECHANISM, and keep one level of abstraction
per axis."

THE DECISION: the six names stay, and the VALUE of
`DEV_SUBCOMMAND_NAMES` is unchanged (`test__dev_group.py` pins it to the
historical literal). What is new is that this module now records WHICH
LEVEL each name sits at, and §13a (`_abstraction_level.py`) reads that
tiering instead of re-deriving it.

REJECTED — dropping `cron` and `systemd` because they are
mechanism-level. That is the tidy-looking move and it is wrong twice:

  1. This set is a DETECTOR, not a vocabulary. §13 uses it to answer one
     question: "is this self-maintenance command sitting at the top
     level?" A top-level `<pkg> cron install` is precisely the shape the
     operator directive exists to catch, so removing `cron` here would
     stop catching it. That trades real §13 coverage for a point about
     naming, and leaves the fleet's CLIs worse.
  2. `dev cron` and `dev systemd` are a PUBLISHED contract — the
     doctrine's fixed-verb block names them, scitex-dev ships
     `ecosystem dev cron` / `ecosystem dev systemd`, and Phase W aliases
     already forward the old top-level spellings to them. A published
     CLI verb is a MIGRATION, not a rename: alias first, remove later.
     Deleting them from the auditor's vocabulary is the removal half
     with none of the migration.

And a mechanism word is not wrong on its own. `<pkg> dev cron` meaning
"manage MY crontab entries" names an ARTEFACT the package owns — the
same kind of noun as `hooks` (git hooks) or `skills` (skill files).
What is wrong is offering it as a SIBLING of an intent, because siblings
read as alternatives and "run continuously" is not an alternative to
"via crontab". That sibling test — not the word — is what §13a checks.
"""

from __future__ import annotations

import click

# The operator's canonical 6 self-maintenance verbs, tiered by the level
# of abstraction each one sits at (see the module docstring for why the
# SET is unchanged and what the alternative was). Chosen because none is
# plausibly a package's DOMAIN verb (unlike image/ci/pytest/…), so
# flagging them at top level yields near-zero false positives.
#
# The broader package-maintenance set (image/installation/worktree/ci/
# pytest/provenance/list-python-apis) is a deliberate FUTURE extension,
# left OUT of v1: for some packages image/ci is genuinely a domain verb
# (a container tool's `image`, a CI tool's `ci`), so folding it in now
# would false-flag them. Start with the unambiguous 6; widen later once
# per-package allowlists exist.

#: INTENT level — names what the command is FOR, with no scheduler or
#: supervisor welded into the word. `jobs/_kinds.py` settled on `daemon`
#: for exactly this meaning when it split the job-kind enum.
DEV_INTENT_NAMES = frozenset({"daemon"})

#: MECHANISM level — names HOW something runs. Legitimate as a group
#: when it means "manage my crontab / my unit files" (an artefact this
#: package owns); never legitimate as a SIBLING of a `DEV_INTENT_NAMES`
#: entry. §13a (`_abstraction_level.py`) enforces that sibling test.
DEV_MECHANISM_NAMES = frozenset({"cron", "systemd"})

#: OBJECT level — a noun naming a thing the package maintains. Not on
#: the intent/mechanism axis at all, so these never take part in §13a:
#: `skills` is not another way of doing `daemon`, it is a different
#: subject.
DEV_OBJECT_NAMES = frozenset({"hooks", "skills", "shell"})

#: The §13 detector. UNCHANGED in value — the union is exactly the
#: historical literal {"daemon", "cron", "systemd", "hooks", "skills",
#: "shell"}, pinned by test. The tiering above is documentation plus the
#: input to §13a, deliberately not a behaviour change.
DEV_SUBCOMMAND_NAMES = (
    DEV_INTENT_NAMES | DEV_MECHANISM_NAMES | DEV_OBJECT_NAMES
)

__all__ = [
    "DEV_INTENT_NAMES",
    "DEV_MECHANISM_NAMES",
    "DEV_OBJECT_NAMES",
    "DEV_SUBCOMMAND_NAMES",
    "check_dev_command_group",
]


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
