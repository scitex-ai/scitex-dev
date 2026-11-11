"""Source-scope controls use the real Dev and installed SDK command groups."""

import importlib
import shutil
import sys
from copy import copy
from importlib.metadata import distribution
from pathlib import Path

import pytest

from scitex_dev._cli import main
from scitex_dev._cli.audit._summary._audit import _resolve_entry_point
from scitex_dev._cli.audit._summary._dict_root import use_dict_root
from scitex_dev._cli.audit._summary._mounted_owner import MountedOwners
from scitex_dev._cli.audit._summary._walker import _walk


@pytest.fixture
def source_root():
    return Path(__file__).resolve().parents[5]


@pytest.fixture
def sdk_command():
    pytest.importorskip("scitex_sdk")
    command = _resolve_entry_point("scitex-sdk")
    if command is None:
        pytest.skip("SDK console entry point is unavailable in this interpreter")
    return command


@pytest.fixture
def duplicate_metadata(tmp_path):
    """Duplicate actual installed Dev metadata, without fabricating a provider."""
    target = tmp_path / "metadata"
    target.mkdir()
    origin = distribution("scitex-dev")._path
    shutil.copytree(origin, target / origin.name)
    sys.path.insert(0, str(target))
    importlib.invalidate_caches()
    try:
        yield target
    finally:
        sys.path.remove(str(target))
        importlib.invalidate_caches()


def _source(root):
    owners = MountedOwners()
    with use_dict_root(root):
        owners.bind_audited_source(main, "scitex-dev", root, "scitex_dev._cli:main")
    return owners, owners.source_dictionary(main, owners.owner(main))


def _empty_group(command):
    group = copy(command)
    group.commands = {}
    return group


def test_declared_source_dictionary_uses_actual_project_bytes(source_root):
    # Arrange
    owners = MountedOwners()
    expected = source_root / ".scitex/dev/cli-audit-dict.yaml"
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(
            main, "scitex-dev", source_root, "scitex_dev._cli:main"
        )
        source = owners.source_dictionary(main, owners.owner(main))
    # Assert
    assert (source.resource, source.payload) == (expected, expected.read_bytes())


def test_missing_source_root_keeps_original_owner_verdict(source_root):
    # Arrange
    owners = MountedOwners()
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(main, "scitex-dev", None, "scitex_dev._cli:main")
        source = owners.source_dictionary(main, owners.owner(main))
    # Assert
    assert source is None


def test_different_audited_tree_cannot_admit_loaded_source(source_root, tmp_path):
    # Arrange
    owners = MountedOwners()
    # Act
    with use_dict_root(tmp_path):
        owners.bind_audited_source(
            main, "scitex-dev", source_root, "scitex_dev._cli:main"
        )
        source = owners.source_dictionary(main, owners.owner(main))
    # Assert
    assert source is None


def test_wrong_distribution_cannot_admit_loaded_source(source_root):
    # Arrange
    owners = MountedOwners()
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(
            main, "scitex-sdk", source_root, "scitex_dev._cli:main"
        )
        source = owners.source_dictionary(main, owners.owner(main))
    # Assert
    assert source is None


def test_wrong_entry_point_cannot_admit_loaded_source(source_root):
    # Arrange
    owners = MountedOwners()
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(
            main, "scitex-dev", source_root, "scitex_dev._cli:other"
        )
        source = owners.source_dictionary(main, owners.owner(main))
    # Assert
    assert source is None


def test_source_dictionary_cannot_claim_an_actual_peer(source_root, sdk_command):
    # Arrange
    owners, source = _source(source_root)
    # Act
    admitted = source.owns(sdk_command, owners.owner(sdk_command))
    # Assert
    assert admitted is False


def test_peer_callback_cannot_use_root_metadata_as_authority(source_root, sdk_command):
    # Arrange
    owners, source = _source(source_root)
    # Act
    admitted = source.owns(sdk_command, owners.owner(main))
    # Assert
    assert admitted is False


def test_duplicate_real_metadata_keeps_source_ownership_ambiguous(
    source_root, duplicate_metadata
):
    # Arrange
    owners = MountedOwners()
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(
            main, "scitex-dev", source_root, "scitex_dev._cli:main"
        )
        owner = owners.owner(main)
        source = owners.source_dictionary(main, owner)
    # Assert
    assert (owner.ambiguous, source) == (True, None)


def test_root_reentry_restores_only_the_actual_source_owner(source_root, sdk_command):
    # Arrange
    root = _empty_group(main)
    peer = _empty_group(sdk_command)
    peer_sibling = _empty_group(sdk_command)
    peer_sibling.add_command(_empty_group(sdk_command), "creds")
    peer.add_command(_empty_group(main), "creds")
    peer.add_command(peer_sibling, "peer")
    root.add_command(peer, "sdk")
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(
            root, "scitex-dev", source_root, "scitex_dev._cli:main"
        )
        _walk(root, [], findings, "scitex-dev", owners=owners)
    unknown = [
        item.command
        for item in findings
        if item.rule == "§1d" and item.command.endswith(" creds")
    ]
    # Assert
    assert unknown == ["scitex-dev sdk peer creds"]


def test_source_provenance_names_the_audited_command(source_root):
    # Arrange
    root = _empty_group(main)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(source_root):
        owners.bind_audited_source(
            root, "scitex-dev", source_root, "scitex_dev._cli:main"
        )
        _walk(root, [], findings, "scitex-dev", owners=owners)
    line = owners.sources[0]
    # Assert
    assert (
        line.startswith("scitex-dev: cli-audit source subject scitex-dev;"),
        "not an installed RECORD claim" in line,
    ) == (True, True)
