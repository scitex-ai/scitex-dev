"""Real virtual Click groups are discovered once without executing operations."""

import itertools

import click
import pytest

from scitex_dev._cli.audit._summary._audit import _check_introspection
from scitex_dev._cli.audit._summary._command_snapshot import snapshot_commands
from scitex_dev._cli.audit._summary._std_rules import check_deprecated_alias_metadata


def _never_execute(*args, **kwargs):
    raise AssertionError("Command/parameter callback was executed during discovery")


class _VirtualGroup(click.Group):
    def __init__(self, name="owned", children=None):
        super().__init__(name, callback=_never_execute)
        self.virtual = children or {}
        self.discovery_calls = []

    def list_commands(self, context):
        self.discovery_calls.append(("list", context.info_name))
        return [*super().list_commands(context), *self.virtual]

    def get_command(self, context, name):
        self.discovery_calls.append(("get", name))
        if name in self.virtual:
            value = self.virtual[name]
            return value if isinstance(value, click.Command) else value(context)
        return super().get_command(context, name)


def test_uncached_public_children_and_static_fallback_are_frozen_once():
    # Arrange — uncached children are deliberately absent from .commands.
    created = []

    def create(context):
        command = click.Command("dynamic", callback=_never_execute)
        created.append(command)
        return command

    group = _VirtualGroup(children={"dynamic": create})
    static = click.Command("static", callback=_never_execute)
    group.add_command(static)
    # Act
    result = snapshot_commands(group, "owned")
    context = click.Context(result.root)
    first = result.root.get_command(context, "dynamic")
    second = result.root.get_command(context, "dynamic")
    # Assert
    assert (
        result.issues,
        len(created),
        first is second is created[0],
        result.root.commands["static"] is static,
        sorted(group.commands),
    ) == ([], 1, True, True, ["static"])


def test_public_discovery_never_parses_or_invokes_callbacks():
    # Arrange — parsing would invoke the option callback; invoking hits the group callback.
    group = _VirtualGroup(
        children={"child": click.Command("child", callback=_never_execute)}
    )
    group.params.append(
        click.Option(["--mode"], default="owned", callback=_never_execute)
    )
    # Act
    result = snapshot_commands(group, "owned")
    # Assert
    assert (result.issues, sorted(result.root.commands)) == ([], ["child"])


def test_shared_group_bindings_keep_distinct_real_parent_contexts():
    # Arrange
    shared = _VirtualGroup(
        "shared",
        {
            "read": lambda context: click.Command(
                "read",
                help=context.info_name,
                callback=_never_execute,
            )
        },
    )
    root = click.Group("owned", commands={"first": shared, "second": shared})
    # Act
    result = snapshot_commands(root, "owned")
    # Assert
    assert (
        result.root.commands["first"].commands["read"].help,
        result.root.commands["second"].commands["read"].help,
        result.root.commands["first"].callback is shared.callback,
    ) == ("first", "second", True)


@pytest.fixture(params=("missing", "get", "list"))
def broken_group(request):
    class Broken(_VirtualGroup):
        def list_commands(self, context):
            if request.param == "list":
                raise ImportError("private diagnostic must not be rendered")
            return ["unavailable"]

        def get_command(self, context, name):
            if request.param == "get":
                raise ImportError("private diagnostic must not be rendered")
            return None

    expected = {"missing": "missing-command", "get": "get-error", "list": "list-error"}
    return Broken(), expected[request.param]


def test_unresolved_or_raising_discovery_is_typed_and_visible(broken_group):
    # Arrange
    group, expected = broken_group
    # Act
    result = snapshot_commands(group, "owned")
    # Assert
    assert (
        len(result.issues),
        result.issues[0].kind,
        "private diagnostic" in result.issues[0].detail,
    ) == (1, expected, False)


def test_ancestor_cycle_is_bounded_without_changing_the_real_group():
    # Arrange
    group = click.Group("owned")
    group.add_command(group, "repeat")
    # Act
    result = snapshot_commands(group, "owned")
    # Assert
    assert (
        group.commands["repeat"] is group,
        result.root.commands,
        [issue.kind for issue in result.issues],
    ) == (True, {}, ["cycle"])


def test_uncached_infinite_factory_stops_at_the_depth_boundary():
    # Arrange
    class Infinite(_VirtualGroup):
        def list_commands(self, context):
            return ["next"]

        def get_command(self, context, name):
            return Infinite()

    # Act
    result = snapshot_commands(Infinite(), "owned", max_depth=3)
    # Assert
    assert (result.nodes, [issue.kind for issue in result.issues]) == (
        3,
        ["depth-limit"],
    )


def test_node_limit_stops_calling_get_command_instead_of_expanding_remainder():
    # Arrange
    group = _VirtualGroup(
        children={str(i): lambda context: click.Command("child") for i in range(20)}
    )
    # Act
    result = snapshot_commands(group, "owned", max_nodes=3)
    calls = [call for call in group.discovery_calls if call[0] == "get"]
    # Assert
    assert (len(calls), result.nodes, [issue.kind for issue in result.issues]) == (
        2,
        3,
        ["node-limit"],
    )


def test_infinite_advertised_names_are_bounded_before_resolution():
    # Arrange
    class Many(_VirtualGroup):
        def list_commands(self, context):
            return (str(number) for number in itertools.count())

        def get_command(self, context, name):
            return click.Command(name)

    # Act
    result = snapshot_commands(Many(), "owned", max_children=3)
    # Assert
    assert (len(result.root.commands), [issue.kind for issue in result.issues]) == (
        3,
        ["children-limit"],
    )


def test_refusal_to_copy_cannot_mutate_the_production_group():
    # Arrange
    class NoCopy(click.Group):
        def __copy__(self):
            return self

    group = NoCopy("owned", commands={"keep": click.Command("keep")})
    # Act
    result = snapshot_commands(group, "owned")
    # Assert
    assert (result.root, sorted(group.commands), [i.kind for i in result.issues]) == (
        None,
        ["keep"],
        ["copy-error"],
    )


def test_capability_checks_see_the_same_real_virtual_commands():
    # Arrange
    list_tools = click.Command(
        "list-tools", params=[click.Option(["--json"], is_flag=True)]
    )
    mcp = _VirtualGroup("mcp", {"list-tools": list_tools})
    root = _VirtualGroup(
        children={
            "mcp": mcp,
            "list-python-apis": click.Command(
                "list-python-apis", params=[click.Option(["--json"], is_flag=True)]
            ),
            "install-shell-completion": click.Command("install-shell-completion"),
            "print-shell-completion": click.Command("print-shell-completion"),
        }
    )
    # Act
    result = snapshot_commands(root, "owned")
    violations = []
    _check_introspection(result.root, "owned", violations)
    # Assert
    assert (result.issues, violations) == ([], [])


def test_alias_check_uses_real_virtual_target_and_keeps_callback_identity():
    # Arrange — a genuine Click forwarder; discovery must never execute it.
    target = click.Command("read", callback=_never_execute)

    @click.command("old")
    @click.pass_context
    def alias(context):
        return context.forward(target)

    alias._deprecated_alias = {"target": "read", "remove_in": "3.0"}
    root = _VirtualGroup(children={"read": target})
    root.add_command(alias)
    # Act
    result = snapshot_commands(root, "owned")
    violations = []
    check_deprecated_alias_metadata(result.root, "owned", violations)
    # Assert
    assert (violations, result.root.commands["read"].callback is target.callback) == (
        [],
        True,
    )


def test_incomplete_discovery_produces_real_error_tier_findings(broken_group):
    # Arrange (STX-TQ007: one assert per test — severity asserted separately).
    from scitex_dev._cli.audit._summary._command_snapshot import discovery_violations

    group, _kind = broken_group
    snapshot = snapshot_commands(group, "owned")
    # Act
    violations = discovery_violations(snapshot)
    # Assert
    assert [v.rule for v in violations] == ["§1a"]


def test_incomplete_discovery_violation_is_error_severity(broken_group):
    # Arrange (companion to the rule-name test above).
    from scitex_dev._cli.audit._summary._command_snapshot import discovery_violations
    from scitex_dev._cli.audit._summary._severity import severity_of

    group, _kind = broken_group
    snapshot = snapshot_commands(group, "owned")
    # Act
    violations = discovery_violations(snapshot)
    # Assert
    assert [(v.rule, severity_of(v)) for v in violations] == [("§1a", "error")]


def test_lazy_dict_group_resolves_through_public_protocol():
    # Arrange — a SAC-style lazy group: dict keys EMPTY, public
    # protocol advertises + resolves without executing callbacks.
    import click

    real = click.Command("list-python-apis", callback=_never_execute)
    lazy = click.Command("mcp-real", callback=_never_execute)

    class LazyDictGroup(click.Group):
        def list_commands(self, ctx):
            return ["list-python-apis", "mcp"]

        def get_command(self, ctx, name):
            if name == "list-python-apis":
                return real
            if name == "mcp":
                return click.Group("mcp")
            return super().get_command(ctx, name)

    group = LazyDictGroup(name="pkg")
    group.commands = {}  # lazy: nothing stored, like _LazyCommandsDict pre-access
    # Act
    result = snapshot_commands(group, "pkg")
    # Assert — snapshot finds both WITHOUT executing callbacks.
    assert result.root is not None
    names = (
        result.root.list_commands(click.Context(result.root))
        if isinstance(result.root, click.Group)
        else []
    )
    assert "list-python-apis" in names
    assert "mcp" in names
    assert not any(i.kind == "missing-command" for i in result.issues)
