"""Shared Click deprecation helper — the 3-phase ladder (W → E → R).

Implements the doctrine in
``scitex_dev/_skills/general/03_interface/02_cli/11_deprecation.md``
(slice 2 of the CLI-standardization plan):

* **Phase W (warn + forward)** — the old name stays as a *hidden* alias
  that re-dispatches all args/options to the new command, printing the
  doctrine-format warning to stderr **once per shell session** (keyed by
  the parent shell's PID via a marker file under
  ``${XDG_RUNTIME_DIR:-/tmp}``)::

      'show-status' is deprecated — use 'status' (removed in v0.20)

* **Phase E (error)** — the old name prints a ``Re-run with:`` redirect
  to stderr and exits ``2``. It no longer forwards.

* **Phase R (removed)** — do not call this helper at all; delete the
  alias and let Click's unknown-command error fire.

Every alias carries ``cmd._deprecated_alias = {"target", "remove_in",
"phase"}`` so the CLI auditor (slice 4) can verify the ladder statically
instead of probing behaviorally. Private ``_deprecated_alias_binding`` also
records actual helper inputs and phase; display text is not a forwarding route.
Auditors resolve that evidence only in their effective command snapshot.

Usage::

    import click
    from scitex_dev.ecosystem import deprecated_alias

    @click.group()
    def main():
        pass

    @main.command("status")
    def status_cmd():
        ...

    deprecated_alias(main, "show-status", target="status", remove_in="0.20")
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass
from pathlib import Path

import click

__all__ = ["deprecated_alias"]

_PHASES = ("warn", "error")

# Raw-passthrough parsing for the alias: unknown options and extra
# positionals all land in ``ctx.args`` in original order, so the target
# command can re-parse them faithfully.
_FORWARD_CONTEXT_SETTINGS = {
    "ignore_unknown_options": True,
    "allow_extra_args": True,
}


@dataclass(frozen=True)
class _AliasBinding:
    """Actual helper inputs; only warn phase forwards, error phase redirects."""

    group: click.Group
    target: click.Command | str | tuple[str, ...]
    phase: str


def _marker_path(old_name: str) -> Path:
    """Once-per-shell-session marker file (doctrine §5/§5a).

    ``${XDG_RUNTIME_DIR:-/tmp}/scitex-cli-dep-${USER}-${PPID}-<cmd>.flag``
    — keyed by the *parent* shell's PID so one warning fires per
    interactive shell, not per CLI invocation.
    """
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = os.environ.get("USER", "unknown")
    return Path(base) / f"scitex-cli-dep-{user}-{os.getppid()}-{old_name}.flag"


def _warn_once(old_name: str, message: str) -> None:
    """Emit ``message`` to stderr unless this shell session already saw it."""
    marker = _marker_path(old_name)
    if marker.exists():
        return
    click.echo(message, err=True)
    try:
        marker.touch()
    except OSError:
        # An unwritable marker dir must never break the forwarded
        # command. The visible consequence is a warning on every
        # invocation instead of once per session — noisier, not masked.
        pass


def _display_name(
    target: click.Command | str | tuple[str, ...], target_name: str | None
) -> str:
    """The new-command name shown in warnings / redirects."""
    if target_name is not None:
        return target_name
    if isinstance(target, tuple):
        return " ".join(target)
    if isinstance(target, str):
        return target
    return target.name or ""


def _resolve_target(
    ctx: click.Context,
    group: click.Group,
    target: click.Command | str | tuple[str, ...],
    display: str,
) -> click.Command:
    """Resolve ``target`` to a command object at dispatch time.

    A string target is looked up on ``group`` lazily so registration
    order does not matter. A missing target is a wiring bug — fail loud
    (exit 2 via UsageError), never fall through silently.
    """
    if isinstance(target, click.Command):
        return target
    name = target[0] if isinstance(target, tuple) else target
    resolved = group.get_command(ctx.parent or ctx, name)
    if resolved is None:
        ctx.fail(
            f"deprecated alias misconfigured: target command {display!r} is not registered"
        )
    return resolved


def _targets_a_group(target: click.Command | str | tuple[str, ...]) -> bool:
    """Is *target* a group we can classify at registration time?

    A string target resolves lazily at dispatch, so it cannot be
    classified here; treat it as a leaf, which preserves the behaviour
    every existing string alias already has.
    """
    return isinstance(target, (click.Group, tuple))


def deprecated_alias(
    group: click.Group,
    old_name: str,
    *,
    target: click.Command | str | tuple[str, ...],
    remove_in: str,
    phase: str = "warn",
    target_name: str | None = None,
) -> click.Command:
    """Register ``old_name`` on ``group`` as a deprecation alias.

    Args:
        group: the Click group the alias is registered on.
        old_name: the deprecated command name.
        target: the new command — a ``click.Command`` object (may live
            on a *different* group) or a name resolved on ``group`` at
            dispatch time. A tuple resolves a nested command path lazily through
            native Click contexts and effective get_command policy; its help is forwarded.
            Tuple tokens are a trusted canonical argv prefix, not shell text.
        remove_in: the version the alias disappears in (``"0.20"`` or
            ``"v0.20"`` — normalized to ``v0.20`` in messages).
        phase: ``"warn"`` (hidden alias forwards + once-per-shell stderr
            warning) or ``"error"`` (stderr redirect, exit 2).
        target_name: override the new-command name shown in messages
            (e.g. ``"ecosystem audit-docs"`` when the target lives on a
            sibling group). Defaults to the target's own name.

    Returns:
        The registered (hidden) alias command, carrying
        ``_deprecated_alias`` metadata for the static auditor.
    """
    if phase not in _PHASES:
        raise ValueError(
            f"deprecated_alias: unknown phase {phase!r} "
            f"(expected one of {_PHASES}; Phase R means: delete the alias)"
        )

    if isinstance(target, tuple) and (
        not target
        or any(
            not isinstance(part, str) or not part or any(c.isspace() for c in part)
            for part in target
        )
    ):
        raise ValueError(
            "deprecated_alias: target path must contain nonempty command tokens"
        )
    display = _display_name(target, target_name)
    version = f"v{str(remove_in).lstrip('vV')}"

    if phase == "warn":

        @click.pass_context
        def _forward(ctx: click.Context) -> None:
            _warn_once(
                old_name,
                f"'{old_name}' is deprecated — use '{display}' "
                f"(removed in {version})",
            )
            target_cmd = _resolve_target(ctx, group, target, display)
            # Re-parse the raw argv through the target so its own
            # options/arguments apply (ctx.invoke(target, *ctx.args)
            # would pass raw tokens positionally and drop options).
            args = list(ctx.args)
            if isinstance(target, tuple):
                # Invoke from the first real group so its callbacks/context run.
                args = [*target[1:], *args]
            info_name = target[0] if isinstance(target, tuple) else display
            sub_ctx = target_cmd.make_context(info_name, args, parent=ctx.parent)
            with sub_ctx:
                target_cmd.invoke(sub_ctx)

        cmd = click.Command(
            old_name,
            callback=_forward,
            params=[],
            hidden=True,
            short_help=f"(deprecated) Use '{display}'.",
            help=(f"(deprecated) Forwards to '{display}'. " f"Removed in {version}."),
            # A GROUP alias must hand `--help` to the target, or the old
            # spelling stops being usable the moment anyone asks it what
            # it can do. Click's own help option fires during PARSING, so
            # with it installed `<old> <verb> --help` never reaches the
            # callback: click prints the ALIAS's two-line help and exits,
            # swallowing `<verb>` without an error. Measured 2026-08-03 —
            # `scitex-dev skills self-explain --help` answered "(deprecated)
            # Forwards to 'dev skills'" and listed no verbs, while the same
            # command WITHOUT --help forwarded correctly. Suppressing the
            # option drops `--help` into ctx.args, which _forward re-parses
            # through the target.
            #
            # Tuple paths also forward help; their first real group resolves
            # the remaining path with native Click contexts and policy.
            add_help_option=not _targets_a_group(target),
            context_settings=dict(_FORWARD_CONTEXT_SETTINGS),
        )
    else:  # phase == "error"

        @click.pass_context
        def _error_redirect(ctx: click.Context) -> None:
            prog = ctx.find_root().info_name or ""
            new_path = f"{prog} {display}".strip()
            click.echo(
                f"error: `{ctx.command_path}` was renamed to "
                f"`{new_path}`.\nRe-run with: {new_path}",
                err=True,
            )
            ctx.exit(2)

        cmd = click.Command(
            old_name,
            callback=_error_redirect,
            params=[],
            hidden=True,
            short_help=f"(deprecated) Use '{display}'.",
            help=f"(deprecated) Renamed to '{display}'. Removed in {version}.",
            context_settings=dict(_FORWARD_CONTEXT_SETTINGS),
        )

    # Static-audit metadata (slice 4 reads this instead of probing).
    cmd._deprecated_alias = {
        "target": display,
        "remove_in": remove_in,
        "phase": phase,
    }
    cmd._deprecated_alias_binding = _AliasBinding(group, target, phase)
    group.add_command(cmd, old_name)
    return cmd
