"""Real filesystem and isolated CLI controls for shared CI resource staging."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scitex_dev.ci._stage_resource import _stage_resource

_RESOURCE = Path(__file__).resolve().parents[2] / "src/scitex_dev/ci/owned_context.sh"
_SCRIPT = _RESOURCE.with_name("_stage_resource.py")
_EXPECTED = "a795678455d409e076a1c93a4a810b50c89499fcb83ae4c90a8d31a19e90e5d1"


def test_real_owned_resource_stages_through_isolated_cli(tmp_path):
    # Arrange
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    destination = root / "owned_context.sh"
    raw = _RESOURCE.read_bytes()
    digest = _EXPECTED
    # Act
    result = subprocess.run(
        [sys.executable, "-I", str(_SCRIPT), "--source", str(_RESOURCE),
         "--destination", str(destination), "--sha256", digest],
        capture_output=True, text=True, timeout=15,
    )
    # Assert
    assert (result.returncode, result.stdout,
            destination.read_bytes() if destination.exists() else None,
            destination.stat().st_mode & 0o777 if destination.exists() else None) == (
        0, "", raw, 0o600
    ), result.stderr


def _destination_case(tmp_path, obstacle):
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    sentinel = tmp_path / "foreign"
    sentinel.write_bytes(b"preserve")
    destination = root / "resource"
    if obstacle == "file":
        destination.write_bytes(b"existing")
    elif obstacle == "symlink":
        destination.symlink_to(sentinel)
    elif obstacle == "parent-symlink":
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        destination = alias / "resource"
    else:
        root.chmod(0o750)
    return root, sentinel, destination


def _refused(source, destination, digest):
    try:
        _stage_resource(source, destination, digest)
    except (OSError, ValueError):
        return True
    return False


@pytest.mark.parametrize("obstacle", ["file", "symlink", "parent-symlink", "parent-mode"])
def test_unsafe_destination_is_refused_without_changing_foreign_data(tmp_path, obstacle):
    # Arrange
    root, sentinel, destination = _destination_case(tmp_path, obstacle)
    # Act
    refused = _refused(_RESOURCE, destination, _EXPECTED)
    # Assert
    assert (refused, sentinel.read_bytes(), (root / "resource").read_bytes()
            if (root / "resource").exists() else None) == (
        True, b"preserve", {"file": b"existing", "symlink": b"preserve"}.get(obstacle)
    )


def _source_case(tmp_path, input_kind):
    source = tmp_path / "input"
    digest = hashlib.sha256(b"reviewed").hexdigest()
    if input_kind == "tampered":
        source.write_bytes(b"changed")
    elif input_kind == "symlink":
        source.symlink_to(_RESOURCE)
    elif input_kind == "fifo":
        os.mkfifo(source)
    elif input_kind == "directory":
        source.mkdir()
    else:
        with source.open("wb") as stream:
            stream.truncate(1024 * 1024 + 1)
    return source, digest


@pytest.mark.parametrize("input_kind", ["tampered", "symlink", "fifo", "directory", "oversized"])
def test_unsafe_source_is_refused_before_destination_creation(tmp_path, input_kind):
    # Arrange
    source, digest = _source_case(tmp_path, input_kind)
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    destination = root / "resource"
    # Act
    refused = _refused(source, destination, digest)
    # Assert
    assert (refused, destination.exists()) == (True, False)


@pytest.mark.parametrize("digest", ["", "z" * 64, "A" * 64, "0" * 63])
def test_malformed_digest_does_not_create_a_file(tmp_path, digest):
    # Arrange
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    destination = root / "resource"
    # Act
    refused = _refused(_RESOURCE, destination, digest)
    # Assert
    assert (refused, destination.exists()) == (True, False)


def test_programmatic_staging_returns_receipt_for_actual_private_file(tmp_path):
    # Arrange
    root = tmp_path / "owned"
    root.mkdir(mode=0o700)
    destination = root / "resource"
    # Act
    receipt = _stage_resource(_RESOURCE, destination, _EXPECTED)
    # Assert
    assert (receipt, hashlib.sha256(destination.read_bytes()).hexdigest(),
            destination.stat().st_mode & 0o777) == (
        {"path": str(destination), "sha256": _EXPECTED, "bytes": _RESOURCE.stat().st_size},
        _EXPECTED, 0o600
    )
