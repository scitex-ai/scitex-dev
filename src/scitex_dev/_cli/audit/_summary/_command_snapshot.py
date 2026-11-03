"""A bounded, per-audit view of Click's public command discovery protocol.

Group.commands is an implementation cache, not the command surface. Resolve
list_commands/get_command using real contexts before the existing rule walkers
run. Copies preserve command classes, callbacks and owner metadata. The audit
does not rewrite original mappings; public discovery may populate an owner's
legitimate lazy cache. Command/parameter callbacks are never invoked.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass
from itertools import islice
from types import MethodType

import click


@dataclass(frozen=True)
class DiscoveryIssue:
    """An explicit boundary where the advertised surface could not be inspected."""

    path: tuple[str, ...]
    kind: str
    detail: str


@dataclass
class CommandSnapshot:
    """Frozen real-command view and its discovery evidence."""

    root: click.Command | None
    issues: list[DiscoveryIssue]
    nodes: int


def _names(group, context):
    # Public discovery protocol FIRST: lazy groups (e.g. SAC LazyGroup)
    # populate ``commands`` only on by-name access, so dict keys undercount
    # the tree. list_commands(ctx) is the advertised surface.
    try:
        names = list(group.list_commands(context))
    except Exception:
        names = []
    seen = set(names)
    for key in group.commands:
        if key not in seen:
            seen.add(key)
            names.append(key)
    return names


def _command(group, context, name):
    # Same ordering: context-bound get_command resolves lazy entries;
    # direct dict access is the fallback for exotic mappings.
    try:
        command = group.get_command(context, name)
    except Exception:
        command = None
    if command is None:
        command = group.commands.get(name)
    if command is None and context.token_normalize_func is not None:
        try:
            command = group.get_command(
                context, context.token_normalize_func(name)
            )
        except Exception:
            command = None
        if command is None:
            command = group.commands.get(context.token_normalize_func(name))
    return command


def snapshot_commands(
    root: click.Command,
    name: str,
    *,
    max_depth: int = 32,
    max_nodes: int = 5000,
    max_children: int = 1000,
) -> CommandSnapshot:
    """Freeze each reachable binding once; retain typed incomplete-discovery errors.

    Shared objects can occur under different context paths. They are inspected
    independently there; an ancestor cycle or a factory returning infinite new
    groups is bounded and reported, never silently treated as a clean leaf.
    """
    if min(max_depth, max_nodes, max_children) < 1:
        raise ValueError("Command discovery bounds must be positive")
    issues = []
    nodes = 0

    def issue(path, kind, detail):
        issues.append(DiscoveryIssue(path, kind, detail))

    def visit(command, path, parent_context, ancestors):
        nonlocal nodes
        if nodes >= max_nodes:
            issue(path, "node-limit", f"command inventory exceeds {max_nodes} nodes")
            return None
        if len(path) > max_depth:
            issue(path, "depth-limit", f"command inventory exceeds depth {max_depth}")
            return None
        if not isinstance(command, click.Command):
            issue(path, "invalid-command", type(command).__name__)
            return None
        nodes += 1
        if not isinstance(command, click.Group):
            return command
        if id(command) in ancestors:
            issue(path, "cycle", "group is already an ancestor of this binding")
            return None
        try:
            frozen = copy(command)
            if frozen is command or type(frozen) is not type(command):
                issue(
                    path,
                    "copy-error",
                    "group did not produce an independent same-class view",
                )
                return None
            frozen.commands = {}
            frozen.list_commands = MethodType(_names, frozen)
            frozen.get_command = MethodType(_command, frozen)
        except Exception as exc:
            issue(path, "copy-error", type(exc).__name__)
            return None
        try:
            settings = dict(command.context_settings or {})
            settings["resilient_parsing"] = True
            context = command.context_class(
                command, info_name=path[-1], parent=parent_context, **settings
            )
        except Exception as exc:
            issue(path, "context-error", type(exc).__name__)
            return frozen
        try:
            with context:
                try:
                    names = list(
                        islice(iter(command.list_commands(context)), max_children + 1)
                    )
                except Exception as exc:
                    issue(path, "list-error", type(exc).__name__)
                    return frozen
                if len(names) > max_children:
                    issue(
                        path,
                        "children-limit",
                        f"group declares more than {max_children} children",
                    )
                    names = names[:max_children]
                seen = set()
                for child_name in names:
                    if not isinstance(child_name, str) or not child_name:
                        issue(path, "invalid-name", type(child_name).__name__)
                        continue
                    if child_name in seen:
                        continue
                    seen.add(child_name)
                    child_path = path + (child_name,)
                    if nodes >= max_nodes:
                        issue(
                            child_path,
                            "node-limit",
                            f"command inventory exceeds {max_nodes} nodes",
                        )
                        break
                    try:
                        child = command.get_command(context, child_name)
                    except Exception as exc:
                        issue(child_path, "get-error", type(exc).__name__)
                        continue
                    if child is None:
                        issue(
                            child_path,
                            "missing-command",
                            "declared name did not resolve",
                        )
                        continue
                    child_view = visit(
                        child, child_path, context, ancestors + (id(command),)
                    )
                    if child_view is not None:
                        frozen.commands[child_name] = child_view
        except Exception as exc:
            issue(path, "context-close-error", type(exc).__name__)
        return frozen

    return CommandSnapshot(visit(root, (name,), None, ()), issues, nodes)


def discovery_violations(snapshot: CommandSnapshot) -> list:
    """Render incomplete discovery through the existing mandatory §1a policy."""
    from ._audit import Violation

    return [
        Violation(
            " ".join(issue.path),
            "§1a",
            f"command discovery {issue.kind}: {issue.detail}",
        )
        for issue in snapshot.issues
    ]
