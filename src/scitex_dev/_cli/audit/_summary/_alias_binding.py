"""Bounded alias evidence over effective command snapshots, without invocation.

Helper bindings describe actual forwarding inputs. Legacy display metadata only
names a suggested reference. Neither proves output correctness or readiness.
"""

from __future__ import annotations

import shlex

import click

from ...._ecosystem.click_compat import _AliasBinding


def _original(command):
    return getattr(command, "_audit_original_command", command)


def helper_binding(command):
    """Reject stale/copied metadata without calling or authenticating Python.

    Identity associates the record with the actual factory callback only; it
    is not cryptographic provenance or isolation from hostile in-process code.
    """
    binding = getattr(command, "_deprecated_alias_binding", None)
    if (
        type(binding) is _AliasBinding
        and binding.callback is vars(command).get("callback")
        and binding.callback is vars(_original(command)).get("callback")
    ):
        return binding
    return None


def _nodes(root):
    """Retain shared-object bindings while bounding malformed command graphs."""
    pending = [(root, ())]
    count = 0
    while pending:
        command, ancestors = pending.pop()
        count += 1
        if count > 5000 or len(ancestors) > 32 or id(command) in ancestors:
            raise ValueError("unbounded command graph")
        yield command
        if isinstance(command, click.Group):
            pending.extend(
                (child, (*ancestors, id(command)))
                for child in command.commands.values()
            )


def _fixed_options(command, arguments):
    """Parse supplied scalar options in a neutral Click parser only.

    Never call original make_context, type conversion, default factories or
    parameter/command callbacks. Unsupported parameter semantics refuse proof.
    """
    if not arguments:
        return True
    if type(command) is not click.Command:
        return False
    params = []
    choices = {}
    for param in command.params:
        if (
            type(param) is not click.Option
            or param.callback is not None
            or param.is_eager
            or callable(param.default)
            or param.envvar is not None
            or param.prompt
            or param.nargs != 1
            or param.multiple
            or param.count
        ):
            return False
        if (
            type(param.type) is click.types.BoolParamType
            and param.is_flag
            and (
                type(param.flag_value) is bool
                or param.flag_value is click.Option(["--flag"], is_flag=True).flag_value
            )
        ):
            option = click.Option(
                [*param.opts, *param.secondary_opts],
                is_flag=True,
                default=None,
                flag_value=param.flag_value,
            )
        elif type(param.type) is click.types.StringParamType and not param.is_flag:
            option = click.Option(param.opts, type=click.STRING, default=None)
        elif (
            type(param.type) is click.Choice
            and not param.is_flag
            and type(param.type.case_sensitive) is bool
            and type(param.type.choices) in (list, tuple)
            and 0 < len(param.type.choices) <= 100
            and all(type(value) is str for value in param.type.choices)
        ):
            option = click.Option(param.opts, type=click.STRING, default=None)
            choices[option.name] = (
                tuple(param.type.choices),
                param.type.case_sensitive,
            )
        else:
            return False
        params.append(option)
    neutral = click.Command("reference", params=params, add_help_option=False)
    context = click.Context(neutral)
    try:
        # Raw option parsing does not call Parameter.process_value/type.convert.
        values, remaining, _order = neutral.make_parser(context).parse_args(
            list(arguments)
        )
        if remaining:
            return False
        for name, (allowed, sensitive) in choices.items():
            if name not in values:
                continue
            value = values[name]
            if type(value) is not str:
                return False
            if not sensitive:
                value = value.casefold()
                allowed = tuple(item.casefold() for item in allowed)
            if value not in allowed:
                return False
        return True
    except click.ClickException:
        return False
    finally:
        context.close()


def _path(start, parts):
    """Resolve only effective stored bindings, then validate fixed leaf argv."""
    node = start
    consumed = 0
    for index, part in enumerate(parts):
        if not isinstance(node, click.Group):
            return node if _fixed_options(node, parts[index:]) else None
        node = node.commands.get(part)
        if node is None:
            return None
        consumed += 1
    return node if consumed else None


def resolve_binding(root, command, parent, *, require_warn=True, _seen=()):
    """Return a uniquely bound effective target, never an alternate rescue path."""
    binding = helper_binding(command)
    if (
        binding is None
        or (require_warn and binding.phase != "warn")
        or id(command) in _seen
        or len(_seen) >= 32
    ):
        return None
    try:
        nodes = list(_nodes(root))
        target = binding.target
        if isinstance(target, click.Command):
            candidates = [node for node in nodes if _original(node) is target]
        else:
            parts = target if isinstance(target, tuple) else (target,)
            groups = (
                [parent]
                if parent is not None and _original(parent) is binding.group
                else [node for node in nodes if _original(node) is binding.group]
            )
            candidates = [_path(group, parts) for group in groups]
        if not candidates or any(node is None for node in candidates):
            return None
        # Different admitted paths to the exact same original object are one
        # target. Matching names/callbacks are deliberately not identity proof.
        if len({id(_original(node)) for node in candidates}) != 1:
            return None
        target = candidates[0]
        if getattr(target, "_deprecated_alias_binding", None) is not None:
            return resolve_binding(
                root,
                target,
                None,
                require_warn=require_warn,
                _seen=(*_seen, id(command)),
            )
        return target
    except (TypeError, ValueError, AttributeError):
        return None


def effective_flags(root, command, parent):
    """Use flags from known warn forwarding only; display text grants nothing."""
    from ._audit import _flag_names

    if getattr(command, "_deprecated_alias_binding", None) is None:
        return _flag_names(command)
    command = resolve_binding(root, command, parent)
    if command is None:
        return set()
    flags = _flag_names(command)
    # An alias cannot turn a custom/eager/callback-driven JSON parameter into
    # supported metadata. No conversion or callback is run to infer behavior.
    json_options = [
        param for param in command.params if "--json" in getattr(param, "opts", ())
    ]
    if len(json_options) != 1 or not (
        type(json_options[0]) is click.Option
        and type(json_options[0].type) is click.types.BoolParamType
        and json_options[0].is_flag
        and json_options[0].callback is None
        and not json_options[0].is_eager
        and not callable(json_options[0].default)
    ):
        flags.discard("--json")
    return flags


def reference_exists(root, parent, target):
    """Check legacy redirect reference syntax, not callback equivalence."""
    try:
        parts = shlex.split(target)
        if not parts or len(parts) > 64:
            return False
        starts = [parent, root] if parent is not None else [root]
        if any(_path(start, parts) is not None for start in starts):
            return True
        # Preserve the old single-name legacy reference contract. Structured
        # forwarding bindings never take this weaker any-depth fallback.
        return len(parts) == 1 and any(
            isinstance(node, click.Group) and parts[0] in node.commands
            for node in _nodes(root)
        )
    except (TypeError, ValueError, AttributeError):
        return False
