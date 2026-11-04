"""Real Click routes and no-callback redirect-reference controls."""

from __future__ import annotations

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli.audit._summary._alias_binding import (
    reference_exists,
    resolve_binding,
)
from scitex_dev._cli.audit._summary._audit import _check_introspection
from scitex_dev._cli.audit._summary._command_snapshot import snapshot_commands
from scitex_dev._cli.audit._summary._std_rules import check_deprecated_alias_metadata
from scitex_dev.ecosystem import deprecated_alias


def _tree(*, json_flag=True, phase="warn"):
    root = click.Group("root")
    dev = click.Group("dev")
    params = [click.Option(["--json"], is_flag=True)] if json_flag else []
    leaf = click.Command("catalog", params=params)
    dev.add_command(leaf)
    root.add_command(dev)
    alias = deprecated_alias(
        root, "list-python-apis", target=("dev", "catalog"), remove_in="9", phase=phase
    )
    return root, dev, leaf, alias


def _json_findings(root):
    out = []
    _check_introspection(root, "fixture", out)
    return [v.message for v in out if v.command == "fixture list-python-apis"]


@pytest.mark.parametrize("extra_path", [False, True])
def test_helper_actual_tuple_proves_json_without_display_guess(extra_path):
    # Arrange
    root, dev, leaf, alias = _tree()
    alias._deprecated_alias["target"] = "human display is not the route"
    paths = {False: {}, True: {"another": leaf}}
    dev.commands.update(paths[extra_path])
    # Act
    snapshot = snapshot_commands(root, "fixture")
    findings = _json_findings(snapshot.root)
    # Assert
    assert (findings, snapshot.issues, alias.params) == ([], [], [])


@pytest.mark.parametrize(
    "mode", ["no-json", "error", "display-only", "missing", "disabled"]
)
def test_unproven_or_nonforwarding_route_does_not_gain_json(mode):
    # Arrange
    root, dev, leaf, alias = _tree(
        json_flag=mode != "no-json", phase="error" if mode == "error" else "warn"
    )
    actions = {
        "display-only": lambda: delattr(alias, "_deprecated_alias_binding"),
        "missing": lambda: dev.commands.pop("catalog"),
        "disabled": lambda: dev.commands.pop("catalog"),
    }
    root.add_command(leaf, "rescue")
    actions.get(mode, lambda: None)()
    # Act
    findings = _json_findings(snapshot_commands(root, "fixture").root)
    # Assert
    assert len(findings) == 1


def test_object_target_shared_paths_are_one_identity():
    # Arrange
    root, _dev, leaf, _alias = _tree()
    root.add_command(leaf, "alternate")
    alias = deprecated_alias(root, "old", target=leaf, remove_in="9")
    # Act
    view = snapshot_commands(root, "fixture").root
    target = resolve_binding(view, alias, view)
    # Assert
    assert target is leaf


def test_equal_names_and_callbacks_do_not_prove_object_target():
    # Arrange
    root, _dev, leaf, _alias = _tree()
    other = click.Command(leaf.name, callback=leaf.callback, params=leaf.params)
    alias = deprecated_alias(root, "old", target=other, remove_in="9")
    # Act
    view = snapshot_commands(root, "fixture").root
    target = resolve_binding(view, alias, view)
    # Assert
    assert target is None


def test_alias_cycle_refuses_without_invocation():
    # Arrange
    root = click.Group("root")
    first = deprecated_alias(root, "first", target="second", remove_in="9")
    deprecated_alias(root, "second", target="first", remove_in="9")
    # Act
    view = snapshot_commands(root, "fixture").root
    target = resolve_binding(view, first, view)
    # Assert
    assert target is None


class _ContextPolicy(click.Group):
    def get_command(self, ctx, name):
        return super().get_command(ctx, name) if ctx.params.get("enabled") else None


def test_unobserved_context_policy_cannot_use_raw_owner_mapping():
    # Arrange
    root, _dev, leaf, alias = _tree()
    guarded = _ContextPolicy("dev", commands={"catalog": leaf})
    root.commands["dev"] = guarded
    # Act
    view = snapshot_commands(root, "fixture")
    target = resolve_binding(view.root, alias, view.root)
    # Assert
    assert (target, bool(view.issues)) == (None, True)


def _completion(params=None):
    install = click.Command(
        "install",
        params=(
            params
            if params is not None
            else [
                click.Option(["--dry-run"], is_flag=True),
                click.Option(
                    ["--shell"],
                    type=click.Choice(("bash", "fish", "zsh"), case_sensitive=False),
                ),
            ]
        ),
    )
    return click.Group("completion", commands={"install": install})


@pytest.mark.parametrize("shell", ["bash", "fish", "zsh", "BASH"])
def test_completion_reference_accepts_supplied_bool_and_string_choice(shell):
    # Arrange
    root = _completion()
    reference = f"install --dry-run --shell {shell}"
    # Act
    valid = reference_exists(root, root, reference)
    # Assert
    assert valid is True


@pytest.mark.parametrize(
    "reference",
    [
        "missing --shell bash",
        "install --shell invalid",
        "install --unknown",
        "install --shell",
        "install 'unterminated",
        "install --shell bash unexpected",
    ],
)
def test_bad_fixed_reference_remains_invalid(reference):
    # Arrange
    root = _completion()
    # Act
    valid = reference_exists(root, root, reference)
    # Assert
    assert valid is False


def test_custom_completion_metadata_is_reference_not_forward_binding():
    # Arrange
    root = _completion()
    alias = click.Command("bash", hidden=True)
    alias._deprecated_alias = {
        "target": "install --dry-run --shell bash",
        "phase": "warn",
        "remove_in": "9",
    }
    root.add_command(alias)
    out = []
    # Act
    check_deprecated_alias_metadata(root, "fixture", out)
    target = resolve_binding(root, alias, root)
    # Assert
    assert (out, target) == ([], None)


class _PoisonType(click.ParamType):
    def convert(self, value, param, ctx):
        raise AssertionError("custom conversion must not run")


def _poison(*args):
    raise AssertionError("callback/default must not run")


@pytest.mark.parametrize(
    "option",
    [
        click.Option(["--value"], callback=_poison),
        click.Option(["--value"], is_eager=True, callback=_poison),
        click.Option(["--value"], default=_poison),
        click.Option(["--value"], type=_PoisonType()),
        click.Option(["--value"], envvar="OWNED_UNUSED"),
        click.Option(["--value"], prompt=True),
        click.Option(["--value"], multiple=True),
    ],
)
def test_unsupported_parameters_refuse_without_any_callbacks(option):
    # Arrange
    root = _completion([option])
    # Act
    valid = reference_exists(root, root, "install --value supplied")
    # Assert
    assert valid is False


def test_miswired_string_cannot_be_rescued_by_valid_display():
    # Arrange
    root, _dev, _leaf, _alias = _tree()
    alias = deprecated_alias(
        root, "old", target="catalog", target_name="dev catalog", remove_in="9"
    )
    out = []
    # Act
    check_deprecated_alias_metadata(root, "fixture", out)
    target = resolve_binding(root, alias, root)
    # Assert
    assert (
        target,
        any(v.command == "fixture old" and "not found" in v.message for v in out),
    ) == (None, True)


def test_real_warn_dispatch_refuses_miswire_and_tuple_help_calls_no_operation(tmp_path):
    # Arrange
    root = click.Group("root")
    card = click.Group("card")
    calls = []
    leaf = click.Command(
        "status",
        callback=lambda: calls.append("operation"),
        help="Canonical owned status help.",
    )
    card.add_command(leaf)
    root.add_command(card)
    deprecated_alias(
        root, "miswired", target="status", target_name="card status", remove_in="9"
    )
    deprecated_alias(root, "corrected", target=("card", "status"), remove_in="9")
    runner = CliRunner()
    # Act
    bad = runner.invoke(root, ["miswired"], env={"XDG_RUNTIME_DIR": str(tmp_path)})
    good = runner.invoke(
        root, ["corrected", "--help"], env={"XDG_RUNTIME_DIR": str(tmp_path)}
    )
    # Assert
    assert (
        bad.exit_code,
        "not registered" in bad.output,
        good.exit_code,
        "Canonical owned status help." in good.output,
        calls,
    ) == (2, True, 0, True, [])


def test_error_phase_redirect_validates_reference_without_forward_claim():
    # Arrange
    root, _dev, _leaf, _alias = _tree()
    alias = deprecated_alias(
        root,
        "retired",
        target="catalog",
        target_name="dev catalog",
        phase="error",
        remove_in="9",
    )
    out = []
    # Act
    check_deprecated_alias_metadata(root, "fixture", out)
    target = resolve_binding(root, alias, root)
    # Assert
    assert (out, target) == ([], None)


class _NoMissingTargetLookup(click.Group):
    def get_command(self, ctx, name):
        if name == "missing":
            raise AssertionError("error phase must not resolve its target")
        return super().get_command(ctx, name)


def test_error_callback_never_resolves_missing_target(tmp_path):
    # Arrange
    root = _NoMissingTargetLookup("root")
    deprecated_alias(
        root,
        "retired",
        target="missing",
        target_name="canonical reference",
        phase="error",
        remove_in="9",
    )
    # Act
    result = CliRunner().invoke(
        root, ["retired"], env={"XDG_RUNTIME_DIR": str(tmp_path)}
    )
    # Assert
    assert (result.exit_code, "Re-run with:" in result.output) == (2, True)


@pytest.mark.parametrize(
    "parameter",
    [
        click.Option(["--json"], is_flag=True, callback=_poison),
        click.Option(["--json"], is_flag=True, is_eager=True),
        click.Option(["--json"], is_flag=True, default=_poison),
        click.Option(["--json"], type=_PoisonType()),
    ],
)
def test_custom_json_semantics_do_not_gain_alias_flag_proof(parameter):
    # Arrange
    root, _dev, leaf, _alias = _tree()
    leaf.params = [parameter]
    # Act
    findings = _json_findings(snapshot_commands(root, "fixture").root)
    # Assert
    assert len(findings) == 1


class _DifferentTargets(click.Group):
    def __init__(self, first, second):
        super().__init__("shared", commands={"catalog": first})
        self.first = first
        self.second = second

    def get_command(self, ctx, name):
        if name == "catalog":
            return self.first if ctx.info_name == "left" else self.second
        return super().get_command(ctx, name)


def test_distinct_effective_targets_for_one_bound_group_refuse_ambiguity():
    # Arrange
    first = click.Command("catalog")
    second = click.Command("catalog", callback=first.callback)
    shared = _DifferentTargets(first, second)
    alias = deprecated_alias(shared, "old", target="catalog", remove_in="9")
    root = click.Group("root", commands={"left": shared, "right": shared, "old": alias})
    # Act
    view = snapshot_commands(root, "fixture")
    target = resolve_binding(view.root, alias, view.root)
    # Assert
    assert (target, view.issues) == (None, [])


class _PoisonChoice(click.Choice):
    def convert(self, value, param, ctx):
        raise AssertionError("custom Choice conversion must not run")


class _PoisonCommand(click.Command):
    def make_context(self, *args, **kwargs):
        raise AssertionError("original command context must not run")


def test_choice_subclass_refuses_without_conversion():
    # Arrange
    root = _completion([click.Option(["--shell"], type=_PoisonChoice(["bash"]))])
    # Act
    valid = reference_exists(root, root, "install --shell bash")
    # Assert
    assert valid is False


def test_command_override_refuses_without_original_context():
    # Arrange
    root = click.Group(
        "root",
        commands={
            "install": _PoisonCommand(
                "install", params=[click.Option(["--dry-run"], is_flag=True)]
            )
        },
    )
    # Act
    valid = reference_exists(root, root, "install --dry-run")
    # Assert
    assert valid is False


def test_binding_uses_frozen_effective_group_not_mutated_raw_owner():
    # Arrange
    root, dev, leaf, alias = _tree()
    view = snapshot_commands(root, "fixture").root
    dev.commands.clear()
    # Act
    target = resolve_binding(view, alias, view)
    # Assert
    assert target is leaf
