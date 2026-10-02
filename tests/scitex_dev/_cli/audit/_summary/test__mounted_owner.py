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
    (info / "RECORD").write_text("\n".join(rows) + f"\n{info.name}/RECORD,,\n")
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
