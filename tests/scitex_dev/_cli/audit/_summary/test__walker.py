"""Installed root CLIs use the same verified policy boundary as mounted CLIs."""

import importlib.util
from pathlib import Path

import pytest

from scitex_dev._cli.audit._summary._dict_root import (
    dict_candidate_paths,
    use_dict_root,
)
from scitex_dev._cli.audit._summary._mounted_owner import MountedOwners
from scitex_dev._cli.audit._summary._walker import _walk

_SPEC = importlib.util.spec_from_file_location(
    "_root_owner_control_helpers",
    Path(__file__).with_name("test__mounted_owner.py"),
)
_HELPERS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_HELPERS)
installation = _HELPERS.installation


def test_installed_root_uses_its_verified_dictionary(installation, tmp_path):
    # Arrange
    root = _HELPERS._install(installation, "scitex-owner-control", "owned_cli_control")
    parent, _ = _HELPERS._parent(tmp_path)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(root, [], findings, "control", owners=owners)
    # Assert
    assert (
        _HELPERS._unknown(findings),
        any("via installed RECORD" in source for source in owners.sources),
    ) == ([], True)


@pytest.mark.parametrize(
    "variant", ["unrecorded", "tampered", "missing", "escape", "unhashed"]
)
def test_recorded_root_cannot_borrow_parent_words(installation, tmp_path, variant):
    # Arrange
    root = _HELPERS._install(
        installation, "scitex-owner-control", "owned_cli_control", variant=variant
    )
    parent, _ = _HELPERS._parent(tmp_path, _HELPERS._DICT)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(root, [], findings, "control", owners=owners)
    # Assert
    assert (_HELPERS._unknown(findings), owners.owner(root).source_record_owned) == (
        ["control zorbulate-result"],
        True,
    )


def test_ambiguous_root_reports_conflicting_installed_owners(installation, tmp_path):
    # Arrange
    root = _HELPERS._install(installation, "scitex-owner-control", "owned_cli_control")
    _HELPERS._additional_claim(
        installation, "scitex-owner-control", "owned_cli_control", version="1.0.0"
    )
    parent, _ = _HELPERS._parent(tmp_path, _HELPERS._DICT)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(root, [], findings, "control", owners=owners)
    # Assert
    assert (
        owners.owner(root).ambiguous,
        owners.owner(root).source_record_owned,
        any("ambiguous distribution ownership" in item.message for item in findings),
        "control zorbulate-result" in _HELPERS._unknown(findings),
    ) == (True, True, True, True)


def test_root_policy_context_is_restored_after_walk(installation, tmp_path):
    # Arrange
    root = _HELPERS._install(installation, "scitex-owner-control", "owned_cli_control")
    parent, _ = _HELPERS._parent(tmp_path)
    # Act
    with use_dict_root(parent):
        before = dict_candidate_paths()
        _walk(root, [], [], "control")
        after = dict_candidate_paths()
    # Assert
    assert after == before


def test_unrecorded_source_claims_do_not_create_installed_root_boundary(
    installation, tmp_path
):
    # Arrange
    root = _HELPERS._install(
        installation,
        "scitex-owner-control",
        "owned_cli_control",
        variant="unowned-source",
    )
    _HELPERS._additional_claim(
        installation,
        "scitex-owner-control",
        "owned_cli_control",
        version="1.0.0",
        owned=False,
    )
    parent, _ = _HELPERS._parent(tmp_path, _HELPERS._DICT)
    owners, findings = MountedOwners(), []
    # Act
    with use_dict_root(parent):
        _walk(root, [], findings, "control", owners=owners)
    # Assert
    assert (
        owners.owner(root).ambiguous,
        owners.owner(root).source_record_owned,
        _HELPERS._unknown(findings),
    ) == (True, False, [])
