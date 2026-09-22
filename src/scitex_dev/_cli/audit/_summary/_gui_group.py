"""§12 — canonical `gui {open,serve,status,stop}` command group.

Split out as its own sibling module (same rationale as `_std_rules.py`'s
own split from the legacy-oversized `_audit.py`): keeps each audit
rule-family small and independently readable instead of growing one
file past the repo's own 512-line limit.

Doctrine: ``_skills/general/03_interface/02_cli/19_gui-commands.md``.
Every browser-based surface a package ships — board, dashboard, Django
UI, interactive editor, browser launcher — mounts under ONE group named
`gui`, with fixed verbs `open [SURFACE]` (auto-serve then open browser),
`serve [--port] [--host]` (foreground), `status`, `stop`.

Two independent packages (scitex-writer, figrecipe) each hand-rolled
the ~140-line state-file/pid-liveness pattern behind `gui serve/open/
status/stop` before this rule existed — this audit rule is the
enforcement half of the fix (the shared primitive itself lives at
`scitex_dev.gui_runtime.GuiRuntime`).

Launcher carve-out: the verb-coverage sub-check (b) applies to a `gui`
group that presents a SERVED surface — it declares at least one of the
server-lifecycle verbs (`serve`, `status`, `stop`), or it stays inside
the canonical vocabulary (`open`/`serve`/`status`/`stop`, however
incompletely). A `gui` group with NO server-lifecycle verb AND
non-canonical verbs (`ecosystem gui {list,open,audit}` — a fan-out
launcher for OTHER leaves' GUIs, served by their own packages) is a
registry view, not a server: `serve`/`status`/`stop` stubs there would
be fake commands, and the rule must not demand them.
"""

from __future__ import annotations

import click

from ._alias_remedy import ALIAS_REMEDY_CAVEAT

# Legacy / flat gui-adjacent leaf names the doctrine's "Migration" section
# names or implies (`<cli> gui`, `<cli> board`, `<cli> dashboard`,
# `start-dashboard`-style compounds). `"gui"` itself is only a violation
# when it resolves to a bare LEAF (not a `click.Group`) — a `gui` GROUP is
# the canonical shape and is checked for verb coverage instead.
LEGACY_GUI_LEAF_NAMES = frozenset(
    {
        "gui",
        "start-gui",
        "launch-gui",
        "run-gui",
        "open-gui",
        "show-gui",
        "dashboard",
        "start-dashboard",
        "launch-dashboard",
        "run-dashboard",
        "show-dashboard",
        "board",
        "start-board",
        "launch-board",
        "run-board",
        "show-board",
    }
)

# The four fixed verbs every canonical `gui` group must expose.
REQUIRED_GUI_VERBS = ("open", "serve", "status", "stop")

#: Verbs that imply a SERVED surface: a group declaring any of these is
#: a server group, and the full lifecycle must be present. A group with
#: none of them is a launcher/registry view ONLY when it also carries
#: non-canonical verbs (see the launcher carve-out in the docstring).
_SERVER_LIFECYCLE_VERBS = frozenset({"serve", "status", "stop"})

__all__ = ["LEGACY_GUI_LEAF_NAMES", "REQUIRED_GUI_VERBS", "check_gui_command_group"]


def check_gui_command_group(root: click.BaseCommand, package: str, out: list) -> None:
    """§12 — canonical `gui {open,serve,status,stop}` command group.

    Two sub-checks, applied at every depth in the command tree:

    (a) A legacy/flat gui-adjacent leaf (`start-gui`, `dashboard`,
        `board`, a bare non-group `gui`, ...) is flagged UNLESS it is
        already a properly-deprecated Phase W/E alias — hidden AND
        carrying `_deprecated_alias` metadata (set by
        ``scitex_dev.ecosystem.deprecated_alias``; verified separately
        by §5's `check_deprecated_alias_metadata`). The doctrine's own
        migration path is exactly this: legacy bare leaves become
        Phase W warn-forward aliases for `gui open [SURFACE]` — a
        package that has done that migration must NOT be re-flagged
        here.
    (b) Once a package has a (non-hidden) `gui` GROUP, every one of
        `REQUIRED_GUI_VERBS` must be a registered subcommand — UNLESS
        the group is a fan-out launcher (no server-lifecycle verb AND
        non-canonical verbs present; see the module docstring). A
        launcher's `serve`/`status`/`stop` would be fake commands.

    Walks hidden commands too (unlike the main `_walk` §1-family
    checks) because recognizing an already-migrated Phase W/E alias
    requires inspecting hidden leaves — the exact same reason
    `check_deprecated_alias_metadata` runs its own walker instead of
    reusing `_walk`.
    """
    from ._audit import Violation

    if not isinstance(root, click.Group):
        return

    def _visit(cmd: click.BaseCommand, path: list[str]) -> None:
        name = path[-1]
        name_lc = name.lower()
        full = " ".join([package, *path])
        is_group = isinstance(cmd, click.Group)
        hidden = bool(getattr(cmd, "hidden", False))

        if name_lc == "gui" and is_group:
            if not hidden:
                present = set(cmd.commands)
                if present & _SERVER_LIFECYCLE_VERBS or present <= set(
                    REQUIRED_GUI_VERBS
                ):
                    missing = [v for v in REQUIRED_GUI_VERBS if v not in cmd.commands]
                    if missing:
                        out.append(
                            Violation(
                                full,
                                "§12",
                                "`gui` group is missing required verb(s) "
                                f"{', '.join(missing)} — the canonical group "
                                "is `gui {open,serve,status,stop}` (doctrine "
                                "19_gui-commands.md).",
                            )
                        )
        elif name_lc in LEGACY_GUI_LEAF_NAMES:
            meta = getattr(cmd, "_deprecated_alias", None)
            already_migrated = hidden and meta is not None
            if not already_migrated:
                out.append(
                    Violation(
                        full,
                        "§12",
                        f"legacy gui-adjacent command {name!r} — migrate to "
                        "the canonical `gui {open,serve,status,stop}` group "
                        "(doctrine 19_gui-commands.md 'Migration'); either "
                        "rename to the group shape directly, or register a "
                        "Phase W/E `scitex_dev.ecosystem.deprecated_alias()` "
                        "forwarding to `gui open`." + ALIAS_REMEDY_CAVEAT,
                    )
                )

        if is_group:
            for sub_name, sub in cmd.commands.items():
                _visit(sub, path + [sub_name])

    for top_name, top_cmd in root.commands.items():
        _visit(top_cmd, [top_name])


# EOF
