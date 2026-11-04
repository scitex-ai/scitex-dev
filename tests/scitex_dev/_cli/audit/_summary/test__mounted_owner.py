"""Real installed-metadata controls for mounted CLI dictionary ownership."""

from __future__ import annotations

import base64
import hashlib
import importlib
import sys
from copy import copy

import click
import pytest

from scitex_dev._cli.audit._summary._audit import _classify, _verb_exception_tokens
from scitex_dev._cli.audit._summary._dict_root import (
    dict_candidate_paths,
    use_dict_root,
    use_owner_dict,
)
from scitex_dev._cli.audit._summary._mounted_owner import MountedOwners
from scitex_dev._cli.audit._summary._walker import _walk

_CLI_SOURCE = """import click
@click.group(name="cli", help="Synthetic owner CLI (v0.0.0).")
@click.option("--json", is_flag=True)
@click.option("--help-recursive", is_flag=True)
@click.option("--version", "-V", is_flag=True)
def cli(**kwargs):
    pass
@cli.command("zorbulate-result", help="Produce a synthetic result.")
@click.option("--json", is_flag=True)
@click.option("--dry-run", is_flag=True)
def result(**kwargs):
    pass
"""
_DICT = "transitive_verbs:\n  - zorbulate\n"


def _record(path: str, payload: bytes) -> str:
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=").decode()
    )
    return f"{path},sha256={digest},{len(payload)}"


def _install(root, name, namespace, dictionary=_DICT, variant="valid", loaded=True):
    package = root / namespace
    package.mkdir(exist_ok=True)
    source = package / "__init__.py"
    source.write_text(
        _CLI_SOURCE if loaded else "raise RuntimeError('must not import')\n"
    )
    resource = package / "_cli_audit_dict.yaml"
    resource.write_text(dictionary)
    info = root / (name.replace("-", "_") + "-0.0.0.dist-info")
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.0\n"
    )
    (info / "entry_points.txt").write_text(
        f"[console_scripts]\n{name} = {namespace}:cli\n"
    )
    rows = [_record(f"{namespace}/__init__.py", source.read_bytes())]
    if variant != "unrecorded":
        rows.append(_record(f"{namespace}/_cli_audit_dict.yaml", resource.read_bytes()))
    if variant == "unowned-source":
        rows = rows[1:]
    if variant == "unhashed":
        rows[-1] = f"{namespace}/_cli_audit_dict.yaml,,"
    (info / "RECORD").write_text("\n".join([*rows, f"{info.name}/RECORD,,"]) + "\n")
    if variant == "no-record":
        (info / "RECORD").unlink()
    if variant == "tampered":
        resource.write_text(dictionary + "nouns:\n  - counterfeit\n")
    if variant == "missing":
        resource.unlink()
    if variant == "escape":
        outside = root / "outside-dictionary.yaml"
        outside.write_text(dictionary)
        resource.unlink()
        resource.symlink_to(outside)
    if variant == "package-escape":
        outside = root.parent / (namespace + "-escaped")
        package.rename(outside)
        package.symlink_to(outside, target_is_directory=True)
    importlib.invalidate_caches()
    return importlib.import_module(namespace).cli if loaded else None


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / "installed"
    root.mkdir()
    sys.path.insert(0, str(root))
    try:
        yield root
    finally:
        sys.path.remove(str(root))
        for name in list(sys.modules):
            if name.startswith("owned_cli_control"):
                del sys.modules[name]
        importlib.invalidate_caches()


def _parent(tmp_path, dictionary=""):
    tree = tmp_path / "parent"
    directory = tree / ".scitex/dev"
    directory.mkdir(parents=True)
    (directory / "cli-audit-dict.yaml").write_text(dictionary)
    return tree, click.Group("umbrella")


def _unknown(out):
    return [v.command for v in out if v.rule == "§1d"]


def test_mounted_dictionary_is_owner_scoped_and_registered_name_is_real(
    installation, tmp_path
):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    parent, root = _parent(tmp_path)
    root.add_command(copy(peer), "control")
    root.add_command(click.Command("zorbulate-result"))
    out = []
    owners = MountedOwners()
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella", owners=owners)
    # Assert
    assert (_unknown(out), peer.name, "scitex-owner-control" in owners.sources[0]) == (
        ["umbrella zorbulate-result"],
        "cli",
        True,
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
def test_invalid_resource_cannot_clean_peer_with_parent_words(
    installation, tmp_path, variant
):
    # Arrange
    peer = _install(
        installation, "scitex-owner-control", "owned_cli_control", variant=variant
    )
    parent, root = _parent(tmp_path, _DICT)
    root.add_command(peer, "control")
    out = []
    owners = MountedOwners()
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella", owners=owners)
    # Assert
    assert (_unknown(out), owners.owner(peer).resource) == (
        ["umbrella control zorbulate-result"],
        None,
    )


def test_sibling_owner_does_not_receive_previous_owner_dictionary(
    installation, tmp_path
):
    # Arrange
    first = _install(installation, "scitex-owner-first", "owned_cli_control_first")
    second = _install(
        installation, "scitex-owner-second", "owned_cli_control_second", "nouns: []\n"
    )
    parent, root = _parent(tmp_path)
    root.add_command(first, "control")
    root.add_command(second, "module")
    out = []
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella")
    # Assert
    assert _unknown(out) == ["umbrella module zorbulate-result"]


def test_ambiguous_distribution_is_explicit_and_does_not_inherit_parent(
    installation, tmp_path
):
    # Arrange
    peer = _install(installation, "scitex-owner-first", "owned_cli_control")
    _install(installation, "scitex-owner-second", "owned_cli_control")
    parent, root = _parent(tmp_path, _DICT)
    root.add_command(peer, "control")
    out = []
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella")
    # Assert
    assert _unknown(out) == ["umbrella control", "umbrella control zorbulate-result"]


def test_index_does_not_import_unloaded_entrypoint(installation, tmp_path):
    # Arrange
    _install(
        installation, "scitex-owner-control", "owned_cli_control_unloaded", loaded=False
    )
    parent, root = _parent(tmp_path)
    out = []
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella")
    # Assert
    assert "owned_cli_control_unloaded" not in sys.modules


def test_valid_dictionary_does_not_disable_flag_or_noun_rules(installation, tmp_path):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    peer.add_command(
        click.Command("artifact", params=[click.Option(["--parallel"], is_flag=True)])
    )
    parent, root = _parent(tmp_path)
    root.add_command(peer, "control")
    out = []
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella")
    # Assert
    assert {v.rule for v in out if v.command == "umbrella control artifact"} >= {
        "§1",
        "§2",
    }


def test_owner_scope_restores_parent_when_loaded_dictionary_raises(
    installation, tmp_path
):
    # Arrange
    peer = _install(
        installation,
        "scitex-owner-control",
        "owned_cli_control",
        "transitive_verbs: [12]\n",
    )
    parent, root = _parent(tmp_path, _DICT)
    root.add_command(peer, "control")
    out = []
    caught = False
    # Act
    with use_dict_root(parent):
        before = dict_candidate_paths()
        try:
            _walk(root, [], out, "umbrella")
        except AttributeError:
            caught = True
        after = dict_candidate_paths()
        labels = _classify("zorbulate-result")
    # Assert
    assert (caught, after, labels) == (True, before, {"verb-t"})


def test_verb_exception_tokens_follow_owner_context_and_reset(tmp_path):
    # Arrange
    parent, _root = _parent(tmp_path)
    first = tmp_path / "first.yaml"
    first.write_text(
        "verb_exceptions:\n  - ls  # why: explicit owned compatibility route\n"
    )
    second = tmp_path / "second.yaml"
    second.write_text("verb_exceptions: []\n")
    # Act
    with use_dict_root(parent):
        with use_owner_dict(first, "first", "verified"):
            first_tokens = _verb_exception_tokens()
        with use_owner_dict(second, "second", "verified"):
            second_tokens = _verb_exception_tokens()
        parent_tokens = _verb_exception_tokens()
    # Assert
    assert (first_tokens, second_tokens, parent_tokens) == (
        frozenset({"ls"}),
        frozenset(),
        frozenset(),
    )


def test_owner_undocumented_exception_is_still_reported(installation, tmp_path):
    # Arrange
    peer = _install(
        installation,
        "scitex-owner-control",
        "owned_cli_control",
        _DICT + "verb_exceptions:\n  - ls\n",
    )
    parent, root = _parent(tmp_path)
    root.add_command(peer, "control")
    out = []
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella")
    # Assert
    assert [v.command for v in out if v.rule == "§1f"] == ["umbrella control"]


def test_verified_payload_cannot_be_replaced_after_owner_resolution(
    installation, tmp_path
):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    peer.add_command(click.Command("blorptify-result"))
    parent, root = _parent(tmp_path)
    root.add_command(peer, "control")
    owners = MountedOwners()
    owner = owners.owner(peer)
    owner.resource.write_text("transitive_verbs:\n  - blorptify\n")
    out = []
    # Act
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella", owners=owners)
    # Assert
    assert _unknown(out) == ["umbrella control blorptify-result"]


def test_public_snapshot_preserves_recorded_owner_under_callback_free_mount(
    installation, tmp_path
):
    # Arrange — real metadata, source and hashed dictionary, not owner overrides.
    from scitex_dev._cli.audit._summary._command_snapshot import snapshot_commands

    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    parent, root = _parent(tmp_path)
    root.add_command(peer, "control")
    snapshot = snapshot_commands(root, "umbrella")
    mounted = snapshot.root.commands["control"]
    owners = MountedOwners()
    out = []
    # Act
    with use_dict_root(parent):
        _walk(snapshot.root, [], out, "umbrella", owners=owners)
    # Assert
    assert (
        snapshot.issues,
        snapshot.root.callback,
        mounted.callback is peer.callback,
        owners.owner(mounted) == owners.owner(peer),
        owners.owner(mounted).reason,
        _unknown(out),
        "scitex-owner-control" in owners.sources[0],
    ) == ([], None, True, True, "verified", [], True)


def _additional_claim(root, name, namespace, *, version="0.0.0", suffix="", owned=True):
    """Write another real metadata claimant without loading its entry point."""
    info = root / f"{name.replace('-', '_')}-{version}{suffix}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )
    (info / "entry_points.txt").write_text(
        f"[console_scripts]\n{name} = {namespace}:cli\n"
    )
    rows = []
    if owned:
        source = root / namespace / "__init__.py"
        rows.append(_record(f"{namespace}/__init__.py", source.read_bytes()))
    (info / "RECORD").write_text("\n".join([*rows, f"{info.name}/RECORD,,"]) + "\n")
    return info


@pytest.mark.parametrize(
    "variant", ["valid", "unrecorded", "tampered", "missing", "escape", "unhashed"]
)
def test_foreign_entrypoint_claim_cannot_override_actual_source_owner(
    installation, tmp_path, variant
):
    # Arrange
    peer = _install(
        installation, "scitex-owner-control", "owned_cli_control", variant=variant
    )
    _additional_claim(
        installation, "scitex-foreign-claim", "owned_cli_control", owned=False
    )
    owners = MountedOwners()
    # Act
    owner = owners.owner(peer)
    parent, root = _parent(tmp_path, _DICT)
    root.add_command(peer, "control")
    out = []
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella", owners=owners)
    # Assert
    assert (
        owner.distribution,
        owner.ambiguous,
        owner.source_record_owned,
        len(owner.unowned_source_claims),
        _unknown(out),
        any("unowned entry-point source claim" in line for line in owners.sources),
    ) == (
        "scitex-owner-control",
        False,
        True,
        1,
        [] if variant == "valid" else ["umbrella control zorbulate-result"],
        True,
    )


@pytest.mark.parametrize("version,suffix", [("1.0.0", ""), ("0.0.0", "-other")])
def test_distinct_physical_metadata_owners_remain_ambiguous(
    installation, version, suffix
):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    _additional_claim(
        installation,
        "scitex-owner-control",
        "owned_cli_control",
        version=version,
        suffix=suffix,
    )
    # Act
    owner = MountedOwners().owner(peer)
    # Assert
    assert (
        owner.ambiguous,
        owner.resource,
        "distinct metadata" in owner.reason,
        version in owner.reason,
    ) == (True, None, True, True)


def test_two_source_owners_cannot_be_selected_by_dictionary_validity(installation):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    _additional_claim(installation, "scitex-owner-second", "owned_cli_control")
    # Act
    owner = MountedOwners().owner(peer)
    # Assert
    assert (owner.ambiguous, owner.resource) == (True, None)


def test_repeated_same_physical_metadata_origin_deduplicates(installation):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    info = installation / "scitex_owner_control-0.0.0.dist-info"
    (installation / "same_origin-0.0.0.dist-info").symlink_to(
        info, target_is_directory=True
    )
    # Act
    owner = MountedOwners().owner(peer)
    # Assert
    assert (owner.ambiguous, owner.resource is not None, owner.identity[-1]) == (
        False,
        True,
        str(info.resolve()),
    )


class _OriginDistribution(importlib.metadata.Distribution):
    """Real metadata reader with an unsupported private origin capability."""

    def __init__(self, delegate, origin):
        self.delegate = delegate
        if origin is not None:
            self._path = origin

    def read_text(self, filename):
        return self.delegate.read_text(filename)

    def locate_file(self, path):
        return self.delegate.locate_file(path)


@pytest.mark.parametrize("origin_kind", ["missing", "nonpath", "unresolvable", "file"])
def test_unknown_metadata_origin_blocks_parent_dictionary(
    installation, tmp_path, origin_kind
):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    owners = MountedOwners()
    key = id(peer.callback)
    ep, module, dist = owners._entries[key][0]
    origins = {
        "missing": None,
        "nonpath": str(installation),
        "unresolvable": installation / "absent.dist-info",
        "file": installation / "owned_cli_control/__init__.py",
    }
    owners._entries[key] = [
        (ep, module, _OriginDistribution(dist, origins[origin_kind]))
    ]
    # Act
    owner = owners.owner(peer)
    parent, root = _parent(tmp_path, _DICT)
    root.add_command(peer, "control")
    out = []
    with use_dict_root(parent):
        _walk(root, [], out, "umbrella", owners=owners)
    # Assert
    assert (
        owner.resource,
        owner.source_record_owned,
        "metadata origin unavailable" in owner.reason,
        "umbrella control zorbulate-result" in _unknown(out),
    ) == (None, False, True, True)


def test_distinct_unknown_metadata_objects_do_not_collapse(installation):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    owners = MountedOwners()
    key = id(peer.callback)
    ep, module, dist = owners._entries[key][0]
    owners._entries[key] = [
        (ep, module, _OriginDistribution(dist, None)),
        (ep, module, _OriginDistribution(dist, None)),
    ]
    # Act
    owner = owners.owner(peer)
    # Assert
    assert (owner.ambiguous, owner.resource, "unavailable:" in owner.reason) == (
        True,
        None,
        True,
    )


@pytest.mark.parametrize("entry_order", [(0, 1), (1, 0)])
def test_same_origin_rejected_forwarder_cannot_erase_source_owner(
    installation, entry_order
):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    (installation / "owned_cli_control/forwarder.py").write_text("from . import cli\n")
    importlib.import_module("owned_cli_control.forwarder")
    info = installation / "scitex_owner_control-0.0.0.dist-info"
    entries = [
        "owned = owned_cli_control:cli",
        "forward = owned_cli_control.forwarder:cli",
    ]
    entries = [entries[index] for index in entry_order]
    (info / "entry_points.txt").write_text(
        "[console_scripts]\n" + "\n".join(entries) + "\n"
    )
    # Act
    owner = MountedOwners().owner(peer)
    # Assert
    assert (
        owner.ambiguous,
        owner.resource is not None,
        owner.source_record_owned,
        len(owner.unowned_source_claims),
    ) == (False, True, True, 1)


def test_ambiguous_source_owners_preserve_foreign_claim_diagnostics(installation):
    # Arrange
    peer = _install(installation, "scitex-owner-control", "owned_cli_control")
    _additional_claim(installation, "scitex-owner-second", "owned_cli_control")
    _additional_claim(
        installation, "scitex-foreign-claim", "owned_cli_control", owned=False
    )
    # Act
    owner = MountedOwners().owner(peer)
    # Assert
    assert (
        owner.ambiguous,
        owner.resource,
        len(owner.unowned_source_claims),
        "scitex-foreign-claim" in owner.unowned_source_claims[0],
    ) == (True, None, 1, True)
