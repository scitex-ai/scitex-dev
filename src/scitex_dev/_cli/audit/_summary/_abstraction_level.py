"""§13a — sibling commands must not mix INTENT with MECHANISM.

Split out as its own sibling module (same rationale as `_dev_group.py`
and `_gui_group.py`): each audit rule-family stays small and
independently readable instead of growing one file past the repo's own
512-line limit.

Doctrine: ``_skills/general/03_interface/02_cli/20_dev-commands.md``
§13a. Constitution, §3 Craft: "Name the INTENT, not the MECHANISM — and
keep one level of abstraction per axis."

What this rule actually asks
----------------------------
Sibling commands under one parent are a MENU: click renders them as the
alternatives available at that level. A menu that offers an INTENT
("run this continuously") beside a MECHANISM ("via crontab") is asking
the reader to choose between what they want and how it is done, and
those are not alternatives to each other. The diagnostic, as the
doctrine states it:

    If two sibling names differ only in HOW the thing is done, they are
    ONE intent plus a `--mechanism`-shaped axis, not two groups.

The known-real case, not a heuristic
------------------------------------
This is deliberately NOT a general "detect abstraction levels"
classifier. Nothing can reliably tell an intent from a mechanism by
inspecting an English word; a rule that guesses false-positives on
somebody's legitimate domain noun, and a noisy rule gets excluded and
then deleted. So it ships ONE hand-written axis family, seeded entirely
from vocabulary the fleet has already ruled on:

  * ``jobs/_kinds.py`` — the job-kind taxonomy. Its docstring states
    which spelling is which: ``service`` is "INTENT (runs continuously)
    — already mechanism-agnostic", ``timer`` is "MECHANISM (systemd
    .timer)", ``cron`` is "MECHANISM (crontab)", and ``daemon`` /
    ``periodic`` are the intent-level names it normalises to.
  * ``_dev_group.py`` — the §13 ``dev`` vocabulary, tiered into
    intent / mechanism / object there. Reading those constants rather
    than re-listing the words is what keeps the two rules from drifting
    apart.

Widen ``AXIS_FAMILIES`` when a SECOND real case turns up, never
speculatively.

What is NOT flagged
-------------------
* A mechanism name with no intent sibling. ``<pkg> dev cron`` meaning
  "manage my crontab entries" names an artefact the package owns and is
  a perfectly good group — the violation is the PAIR, not the word.
* Two mechanism names together (``cron`` + ``systemd``). They are the
  same level as each other; the level is only wrong beside an intent.
* An intent and a mechanism in DIFFERENT groups. Nothing is being
  offered as an alternative to anything, so there is no mixed menu.
* Hidden commands, which are not on the menu at all. A Phase W
  warn-forward alias is hidden by construction
  (``scitex_dev.ecosystem.deprecated_alias``), so a package that has
  already migrated ``<pkg> systemd`` to an alias is not re-flagged. That
  is the same escape hatch §12 and §13 grant, obtained here for free.

REPORTING-ONLY, exactly like §12 and §13: this changes nobody's runtime
behaviour. It names the shape and cites the migration path, because a
CLI verb is a published contract — collapsing ``cron`` / ``systemd``
into ``periodic --mechanism`` is a MIGRATION (alias first, remove
later), not a rename.
"""

from __future__ import annotations

from dataclasses import dataclass

import click

from ._dev_group import DEV_INTENT_NAMES, DEV_MECHANISM_NAMES


@dataclass(frozen=True)
class AxisFamily:
    """One axis on which intent-level and mechanism-level names collide.

    ``axis`` is the plain-English question both name sets answer. It is
    quoted back in the finding so the message EXPLAINS why these words
    were grouped together, instead of asserting a classification the
    reader has to take on faith.
    """

    axis: str
    intent: frozenset[str]
    mechanism: frozenset[str]


#: The scheduling / supervision axis — the one the fleet has already
#: ruled on twice (``jobs/_kinds.py`` in the data model, §13 in the CLI).
#:
#: Intent extends §13's ``daemon`` with the two spellings the job-kind
#: taxonomy names as intents: ``service`` (mechanism-agnostic by that
#: module's own docstring — a systemd unit OR a respawn keep-alive loop)
#: and ``periodic`` (the canonical intent spelling ``canonical_kind``
#: resolves to a stored kind). Mechanism extends §13's ``cron`` /
#: ``systemd`` with ``timer``, which the same docstring classifies as
#: the systemd ``.timer`` mechanism for the "run periodically" intent.
SCHEDULING_AXIS = AxisFamily(
    axis="how this package's own jobs are run",
    intent=DEV_INTENT_NAMES | frozenset({"service", "periodic"}),
    mechanism=DEV_MECHANISM_NAMES | frozenset({"timer"}),
)

#: Every axis family checked. ONE entry on purpose — see the module
#: docstring on why this is a curated list and not a classifier.
AXIS_FAMILIES: tuple[AxisFamily, ...] = (SCHEDULING_AXIS,)

__all__ = [
    "AXIS_FAMILIES",
    "SCHEDULING_AXIS",
    "AxisFamily",
    "check_cli_abstraction_level",
]


def _quote(names: list[str]) -> str:
    """``['cron', 'timer']`` -> ``"'cron', 'timer'"``."""
    return ", ".join(repr(n) for n in names)


def _names_verb(names: list[str]) -> str:
    """Subject-verb agreement for a name list rendered inside a message."""
    return "names" if len(names) == 1 else "name"


def check_cli_abstraction_level(
    root: click.BaseCommand, package: str, out: list
) -> None:
    """§13a — sibling groups must not mix intent-level and mechanism-level names.

    Walks every group in the command tree, the root included, and reads
    the VISIBLE direct children of each. When one group's children hold
    both an intent name and a mechanism name from the same
    :data:`AXIS_FAMILIES` entry, ONE violation is emitted against that
    PARENT — not one per offending child, because the defect is the menu
    rather than any single command on it.

    Recursion visits hidden groups too (their subtree can still hold a
    mixed menu), but each group is judged on its visible children only,
    and each group object is judged ONCE: ``deprecated_alias`` mounts the
    very same command object under two names, so an id-keyed guard is
    what stops one mixed menu being reported twice under two paths.
    """
    from ._audit import Violation

    if not isinstance(root, click.Group):
        return

    seen: set[int] = set()

    def _visit(group: click.Group, path: list[str]) -> None:
        if id(group) in seen:
            return
        seen.add(id(group))

        visible = {
            name.lower()
            for name, sub in group.commands.items()
            if not getattr(sub, "hidden", False)
        }
        full = " ".join([package, *path])

        for family in AXIS_FAMILIES:
            intents = sorted(visible & family.intent)
            mechanisms = sorted(visible & family.mechanism)
            if not intents or not mechanisms:
                continue
            out.append(
                Violation(
                    full,
                    "§13a",
                    f"sibling commands mix levels of abstraction — "
                    f"{_quote(intents)} {_names_verb(intents)} an INTENT "
                    f"while {_quote(mechanisms)} {_names_verb(mechanisms)} "
                    f"a MECHANISM for the same axis ({family.axis}), so this "
                    f"group's menu offers 'what' beside 'how'. If two names "
                    f"differ only in HOW the thing is done they are one "
                    f"intent plus a `--mechanism`-shaped axis, not two "
                    f"groups: keep the intent as the command and move the "
                    f"mechanism onto its own option or spec field (doctrine "
                    f"20_dev-commands.md §13a). A published CLI verb is a "
                    f"MIGRATION, not a rename — register a Phase W "
                    f"`scitex_dev.ecosystem.deprecated_alias()` for the old "
                    f"spelling first, remove it later.",
                )
            )

        for name, sub in group.commands.items():
            if isinstance(sub, click.Group):
                _visit(sub, path + [name])

    _visit(root, [])


# EOF
