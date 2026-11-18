"""Fixture device context is observable without replaying release commands."""

import json
import os

import pytest

from ._release_child_observation import OwnedChildObservation
from ._release_device_observation import observe_fixture_device


def test_owned_fixture_context_contains_device_io(tmp_path):
    # Arrange
    observer = OwnedChildObservation(tmp_path)
    # Act
    result = observer._fixture_filesystem()
    # Assert
    assert "device_io" in result



@pytest.fixture
def block_tree(tmp_path):
    base = tmp_path / "blocks"
    device = base / "252:1"
    device.mkdir(parents=True)
    (device / "dev").write_text("252:1\n")
    (device / "stat").write_text(" ".join(str(n) for n in range(17)))
    (device / "slaves").mkdir()
    return base


def test_known_statistics_have_correct_indices(block_tree):
    # Arrange
    device = os.makedev(252, 1)
    # Act
    row = observe_fixture_device(device, block_tree)
    # Assert
    assert row == {"state": "observed", "major": 252, "minor": 1,
                   "statistics": {"reads_completed": 0, "read_ms": 3,
                                  "writes_completed": 4, "write_ms": 7,
                                  "in_flight": 8, "active_ms": 9, "weighted_ms": 10},
                   "direct_backing": {"state": "observed", "devices": []}}


@pytest.mark.parametrize("body", [
    b"", b"0 " * 11, b"0 " * 15, b"0 " * 18, b"secret-marker",
    b"-1 " + b"0 " * 16, b"+1 " + b"0 " * 16,
    b"nan " + b"0 " * 16, b"inf " + b"0 " * 16,
    b"18446744073709551616 " + b"0 " * 16,
    b"\xff " + b"0 " * 16, b" " * 1025,
])
def test_unsupported_statistics_remain_unknown(block_tree, body):
    # Arrange
    (block_tree / "252:1/stat").write_bytes(body)
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row == {"state": "unknown", "reason": "ValueError" if body[:1] != b"\xff" else "UnicodeDecodeError"}


@pytest.mark.parametrize("size, state", [(1024, "observed"), (1025, "unknown")])
def test_stat_read_exact_byte_boundary(block_tree, size, state):
    # Arrange
    body = " ".join("0" for _ in range(17))
    (block_tree / "252:1/stat").write_text(body.ljust(size))
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row["state"] == state


def test_maximum_counter_is_preserved(block_tree):
    # Arrange
    (block_tree / "252:1/stat").write_text(" ".join([str(2**64 - 1)] * 17))
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row["statistics"]["weighted_ms"] == 2**64 - 1


@pytest.mark.parametrize("body", ["secret-device-name", "253:1", "-1:1", "1:2:3", "4294967296:1"])
def test_mismatched_or_invalid_device_is_unknown(block_tree, body):
    # Arrange
    (block_tree / "252:1/dev").write_text(body)
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row == {"state": "unknown", "reason": "ValueError"}


@pytest.mark.parametrize("value", [None, True, -1, "64513", 2**128])
def test_invalid_fixture_device_is_unknown(block_tree, value):
    # Arrange
    root = block_tree
    # Act
    row = observe_fixture_device(value, root)
    # Assert
    assert row["state"] == "unknown"


@pytest.mark.parametrize("name", ["dev", "stat"])
def test_missing_attributes_are_unknown(block_tree, name):
    # Arrange
    (block_tree / "252:1" / name).unlink()
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row == {"state": "unknown", "reason": "FileNotFoundError"}


@pytest.fixture(params=[4, 5])
def backing_tree(block_tree, request):
    for minor in range(request.param):
        node = block_tree / f"259:{minor}"
        node.mkdir()
        (node / "dev").write_text(f"259:{minor}")
        (node / "stat").write_text("0 " * 17)
        (block_tree / "252:1/slaves" / f"secret-backing-name-{minor}").symlink_to(node)
    return block_tree, request.param


def test_direct_backing_count_is_bounded(backing_tree):
    # Arrange
    root, count = backing_tree
    # Act
    row = observe_fixture_device(os.makedev(252, 1), root)
    # Assert
    assert row["direct_backing"]["state"] == ("observed" if count == 4 else "unknown")


def test_backing_names_are_not_returned(backing_tree):
    # Arrange
    root, _ = backing_tree
    # Act
    body = json.dumps(observe_fixture_device(os.makedev(252, 1), root))
    # Assert
    assert "secret-backing-name" not in body


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_nonregular_attributes_are_refused(block_tree, kind):
    # Arrange
    path = block_tree / "252:1/stat"
    path.unlink()
    operations = {"symlink": lambda: path.symlink_to(block_tree / "secret-marker"),
                  "fifo": lambda: os.mkfifo(path), "directory": lambda: path.mkdir()}
    operations[kind]()
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row["state"] == "unknown"


@pytest.mark.parametrize("size, state", [(64, "observed"), (65, "unknown")])
def test_device_attribute_exact_byte_boundary(block_tree, size, state):
    # Arrange
    (block_tree / "252:1/dev").write_text("252:1".ljust(size))
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row["state"] == state


def test_backing_attribute_failure_does_not_fabricate_zero_counters(block_tree):
    # Arrange
    (block_tree / "252:1/slaves/owned-absent").symlink_to(block_tree / "absent")
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert row["direct_backing"] == {"state": "unknown", "reason": "FileNotFoundError"}


def test_backing_topology_is_not_recursed(block_tree):
    # Arrange
    (block_tree / "252:1/slaves/owned-self").symlink_to(block_tree / "252:1")
    # Act
    row = observe_fixture_device(os.makedev(252, 1), block_tree)
    # Assert
    assert "direct_backing" not in row["direct_backing"]["devices"][0]


def test_fixture_sample_selects_its_actual_device(tmp_path):
    # Arrange
    device = tmp_path.stat().st_dev
    identity = f"{os.major(device)}:{os.minor(device)}"
    blocks = tmp_path / "blocks"
    node = blocks / identity
    node.mkdir(parents=True)
    (node / "dev").write_text(identity)
    (node / "stat").write_text(" ".join(str(n) for n in range(17)))
    (node / "slaves").mkdir()
    observer = OwnedChildObservation(tmp_path, sys_block_root=blocks)
    # Act
    row = observer._fixture_filesystem()
    # Assert
    assert row["device_io"]["statistics"]["writes_completed"] == 4
