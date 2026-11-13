"""Run the shipped Bash resource against real owned filesystem fixtures."""

import os
import subprocess
from pathlib import Path

import pytest

RESOURCE = Path(__file__).resolve().parents[2] / "src/scitex_dev/ci/owned_context.sh"
PREFIX = "set -euo pipefail; source \"$1\"; "


def execute(tmp_path, body, *, initialize=True, timeout=15):
    setup = 'owned_context_init "$2" scitex-owned-test-; ' if initialize else ""
    code = PREFIX + setup + body
    return subprocess.run(
        ["bash", "-c", code, "owned-control", str(RESOURCE), str(tmp_path)],
        env={"PATH": os.defpath, "HOME": str(tmp_path)},
        text=True, capture_output=True, timeout=timeout,
    )


def test_success_removes_exact_owned_root(tmp_path):
    # Arrange
    body = 'driver_body() { touch "$OWNED_TMPDIR/result"; }; run_owned_body'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir())) == (0, [])


def test_failure_preserves_body_status(tmp_path):
    # Arrange
    body = 'driver_body() { return 23; }; run_owned_body'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir())) == (23, [])


def test_replacement_is_retained(tmp_path):
    # Arrange
    body = 'driver_body() { mv "$OWNED_TMPDIR" "${OWNED_TMPDIR}.moved"; mkdir "$OWNED_TMPDIR"; touch "$OWNED_TMPDIR/sentinel"; }; run_owned_body'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, len(list(tmp_path.glob("*/sentinel")))) == (1, 1)


def test_redirected_tmpdir_refuses_body(tmp_path):
    # Arrange
    body = 'export TMPDIR="$2" MARKER="$2/executed"; driver_body() { touch "$MARKER"; }; run_owned_body'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir())) == (1, [])


def test_uninitialized_context_refuses_body(tmp_path):
    # Arrange
    body = 'export MARKER="$2/executed"; driver_body() { touch "$MARKER"; }; run_owned_body'
    # Act
    result = execute(tmp_path, body, initialize=False)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir())) == (1, [])


def test_duplicate_initialization_cleans_first_root(tmp_path):
    # Arrange
    body = 'owned_context_init "$2" scitex-owned-test-'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir())) == (1, [])


def test_duplicate_source_cleans_first_root(tmp_path):
    # Arrange
    body = 'source "$1"'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir())) == (1, [])


@pytest.mark.parametrize("entries,allocated,expected", [
    ("10000", "1073741824", "10"),
    ("10001", "0", "60"),
    ("139119", "14646427648", "60"),
    ("200000", "34359738368", "60"),
])
def test_reviewed_capacity_boundaries(tmp_path, entries, allocated, expected):
    # Arrange
    body = f"owned_cleanup_budget {entries} {allocated}"
    # Act
    result = execute(tmp_path, body, initialize=False)
    # Assert
    assert (result.returncode, result.stdout) == (0, expected)


@pytest.mark.parametrize("entries,allocated", [
    ("200001", "0"), ("1", "34359738369"), ("01", "0"),
    ("1", "00"), ("99999999999999999999", "0"), ("-1", "0"),
])
def test_unreviewed_capacity_refused(tmp_path, entries, allocated):
    # Arrange
    body = f"owned_cleanup_budget {entries} {allocated}"
    # Act
    result = execute(tmp_path, body, initialize=False)
    # Assert
    assert result.returncode == 1


def test_real_large_class_cleanup(tmp_path):
    # Arrange
    body = 'driver_body() { for ((i=0;i<10001;i++)); do mkdir "$OWNED_TMPDIR/$i"; done; }; run_owned_body'
    # Act
    result = execute(tmp_path, body, timeout=75)
    # Assert
    assert (result.returncode, list(tmp_path.iterdir()), "budget_seconds=60" in result.stderr) == (0, [], True)


def test_resource_refuses_direct_execution(tmp_path):
    # Arrange
    command = ["bash", str(RESOURCE)]
    # Act
    result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    # Assert
    assert (result.returncode, "source this CI resource" in result.stderr) == (1, True)


def test_initialized_context_executes_marker_body(tmp_path):
    # Arrange
    body = 'export MARKER="$2/executed"; driver_body() { touch "$MARKER"; }; run_owned_body'
    # Act
    result = execute(tmp_path, body)
    # Assert
    assert (result.returncode, (tmp_path / "executed").is_file()) == (0, True)
