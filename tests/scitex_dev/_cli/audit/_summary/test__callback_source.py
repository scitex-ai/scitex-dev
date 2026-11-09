"""Loaded nested callbacks retain their real installed dictionary owner."""

import importlib
import importlib.util
from copy import copy
from pathlib import Path
import sys

import click
import pytest

from scitex_dev._cli.audit._summary._dict_root import use_dict_root
from scitex_dev._cli.audit._summary._mounted_owner import MountedOwners
from scitex_dev._cli.audit._summary._walker import _walk

_SPEC = importlib.util.spec_from_file_location(
    "_nested_callback_control_helpers",
    Path(__file__).with_name("test__mounted_owner.py"),
)
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
installation = _HELPERS.installation


def _mounted(root, tmp_path, dictionary, variant="valid"):
    origin = _HELPERS._install(
        root,
        "scitex-callback-origin",
        "owned_cli_control_origin",
        variant=variant,
    )
    host = _HELPERS._install(
        root,
        "scitex-callback-host",
        "owned_cli_control_host",
        dictionary,
    )
    child = copy(origin.commands["zorbulate-result"])
    host.add_command(child)
    parent, umbrella = _HELPERS._parent(tmp_path)
    umbrella.add_command(host, "host")
    return parent, umbrella, child


def test_nested_callback_uses_its_own_dictionary(installation, tmp_path):
    # Arrange
    parent, umbrella, child = _mounted(installation, tmp_path, "nouns: []\n")
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(umbrella, [], findings, "umbrella", owners=owners)
    owner = owners.owner(child)
    # Assert
    assert (_HELPERS._unknown(findings), getattr(owner, "distribution", None)) == (
        [],
        "scitex-callback-origin",
    )


@pytest.mark.parametrize(
    "variant",
    [
        "unrecorded",
        "tampered",
        "missing",
        "escape",
        "package-escape",
        "unowned-source",
        "unhashed",
        "no-record",
    ],
)
def test_invalid_nested_owner_never_borrows_host_words(installation, tmp_path, variant):
    # Arrange
    parent, umbrella, child = _mounted(installation, tmp_path, _HELPERS._DICT, variant)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(umbrella, [], findings, "umbrella", owners=owners)
    owner = owners.owner(child)
    # Assert
    assert (
        _HELPERS._unknown(findings),
        getattr(owner, "resource", None),
        getattr(owner, "distribution", None),
    ) == (
        ["umbrella host zorbulate-result"],
        None,
        "scitex-callback-origin",
    )


def test_non_click_console_bootstrap_does_not_hide_loaded_callback_owner(
    installation,
    tmp_path,
):
    # Arrange
    namespace = "owned_cli_control_bootstrap"
    _HELPERS._install(installation, "scitex-bootstrap-origin", namespace, loaded=False)
    package = installation / namespace
    source = package / "__init__.py"
    source.write_text(_HELPERS._CLI_SOURCE + "\ndef main():\n    return cli.main()\n")
    info = installation / "scitex_bootstrap_origin-0.0.0.dist-info"
    (info / "entry_points.txt").write_text(
        f"[console_scripts]\norigin = {namespace}:main\n"
    )
    rows = [
        _HELPERS._record(f"{namespace}/__init__.py", source.read_bytes()),
        _HELPERS._record(
            f"{namespace}/_cli_audit_dict.yaml",
            (package / "_cli_audit_dict.yaml").read_bytes(),
        ),
    ]
    (info / "RECORD").write_text("\n".join([*rows, f"{info.name}/RECORD,,"]) + "\n")
    importlib.invalidate_caches()
    command = importlib.import_module(namespace).cli
    # Act
    owner = MountedOwners().owner(command)
    # Assert
    assert (getattr(owner, "distribution", None), getattr(owner, "reason", None)) == (
        "scitex-bootstrap-origin",
        "verified",
    )


def test_ambiguous_nested_source_remains_blocked(installation, tmp_path):
    # Arrange
    parent, umbrella, child = _mounted(installation, tmp_path, _HELPERS._DICT)
    _HELPERS._install(installation, "scitex-second-origin", "owned_cli_control_origin")
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(umbrella, [], findings, "umbrella", owners=owners)
    owner = owners.owner(child)
    # Assert
    assert (
        getattr(owner, "ambiguous", False),
        getattr(owner, "resource", None),
        set(_HELPERS._unknown(findings)),
    ) == (
        True,
        None,
        {"umbrella host zorbulate-result"},
    )


def test_callback_metadata_does_not_import_an_unloaded_module(installation):
    # Arrange
    namespace = "owned_cli_control_unloaded_callback"
    _HELPERS._install(installation, "scitex-unloaded-origin", namespace, loaded=False)

    def unbound():
        pass

    unbound.__module__ = namespace
    command = click.Command("control", callback=unbound)
    # Act
    owner = MountedOwners().owner(command)
    # Assert
    assert (owner, namespace in sys.modules) == (None, False)


def test_unbound_callback_cannot_claim_a_loaded_namespace(installation):
    # Arrange
    namespace = "owned_cli_control_unbound_callback"
    _HELPERS._install(installation, "scitex-unbound-origin", namespace)

    def unbound():
        pass

    unbound.__module__ = namespace
    command = click.Command("control", callback=unbound)
    # Act
    owner = MountedOwners().owner(command)
    # Assert
    assert owner is None


def _module_mount(installation, tmp_path, recorded):
    parent, umbrella, _child = _mounted(installation, tmp_path, _HELPERS._DICT)
    namespace = "owned_cli_control_origin"
    source = installation / namespace / "adapters.py"
    source.write_text(_HELPERS._CLI_SOURCE)
    info = installation / "scitex_callback_origin-0.0.0.dist-info"
    if recorded:
        with (info / "RECORD").open("a") as stream:
            stream.write(
                _HELPERS._record(f"{namespace}/adapters.py", source.read_bytes()) + "\n"
            )
    importlib.invalidate_caches()
    child = importlib.import_module(namespace + ".adapters").cli.commands[
        "zorbulate-result"
    ]
    umbrella.commands["host"].add_command(child)
    return parent, umbrella, child


@pytest.mark.parametrize(
    "recorded,unknown,resource",
    [
        (True, [], True),
        (False, ["umbrella host zorbulate-result"], False),
    ],
)
def test_callback_module_requires_its_own_record_membership(
    installation,
    tmp_path,
    recorded,
    unknown,
    resource,
):
    # Arrange
    parent, umbrella, child = _module_mount(installation, tmp_path, recorded)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(umbrella, [], findings, "umbrella", owners=owners)
    owner = owners.owner(child)
    # Assert
    assert (
        _HELPERS._unknown(findings),
        getattr(owner, "resource", None) is not None,
        getattr(owner, "distribution", None),
    ) == (unknown, resource, "scitex-callback-origin")


def test_namespace_hint_without_loaded_console_source_grants_nothing(installation):
    # Arrange
    namespace = "owned_cli_control_namespace_hint"
    origin = _HELPERS._install(installation, "scitex-namespace-hint", namespace)
    bootstrap = installation / namespace / "bootstrap.py"
    bootstrap.write_text(
        "raise RuntimeError('must not import this console candidate')\n"
    )
    info = installation / "scitex_namespace_hint-0.0.0.dist-info"
    (info / "entry_points.txt").write_text(
        f"[console_scripts]\norigin = {namespace}.bootstrap:main\n"
    )
    # Act
    owner = MountedOwners().owner(origin.commands["zorbulate-result"])
    # Assert
    assert (owner, namespace + ".bootstrap" in sys.modules) == (None, False)


def test_opaque_callable_metadata_is_not_executed():
    # Arrange
    class OpaqueCallback:
        @property
        def __module__(self):
            raise AssertionError("must not inspect a callback descriptor")

        def __call__(self):
            raise AssertionError("must not run a callback")

    command = click.Command("control", callback=OpaqueCallback())
    # Act
    owner = MountedOwners().owner(command)
    # Assert
    assert owner is None


def test_unrecorded_child_of_same_distribution_cannot_use_parent_dictionary(
    installation,
    tmp_path,
):
    # Arrange
    parent, _unused, child = _module_mount(installation, tmp_path, False)
    origin = importlib.import_module("owned_cli_control_origin").cli
    origin.add_command(child)
    umbrella = click.Group("umbrella")
    umbrella.add_command(origin, "origin")
    findings, owners = [], MountedOwners()
    # Act
    with use_dict_root(parent):
        _walk(umbrella, [], findings, "umbrella", owners=owners)
    # Assert
    assert _HELPERS._unknown(findings) == ["umbrella origin zorbulate-result"]


def test_nested_lookup_cannot_rescue_an_already_rejected_resource(
    installation, tmp_path
):
    # Arrange
    origin = _HELPERS._install(
        installation,
        "scitex-rejected-origin",
        "owned_cli_control_rejected",
        variant="tampered",
    )
    owners = MountedOwners()
    rejected = owners.owner(origin)
    (installation / "owned_cli_control_rejected/_cli_audit_dict.yaml").write_text(
        _HELPERS._DICT
    )
    parent, umbrella = _HELPERS._parent(tmp_path)
    umbrella.add_command(origin, "origin")
    findings = []
    # Act
    with use_dict_root(parent):
        _walk(umbrella, [], findings, "umbrella", owners=owners)
    # Assert
    assert (rejected.resource, _HELPERS._unknown(findings)) == (
        None,
        ["umbrella origin zorbulate-result"],
    )
