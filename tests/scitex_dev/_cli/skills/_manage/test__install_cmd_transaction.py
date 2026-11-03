"""Real installed-provider projections preserve foreign and unselected content."""

from __future__ import annotations

import json
import os
import sys

import click
import pytest
from click.testing import CliRunner

from scitex_dev._cli.skills._manage._install_cmd import register
from scitex_dev._ecosystem._skills.skills import list_skills
from scitex_dev.skill_registry import MANIFEST_NAME


@pytest.fixture
def installer():
    @click.group()
    def skills():
        pass

    register(skills)
    return skills


def _install(installer, destination, package, *flags):
    return CliRunner().invoke(
        installer,
        [
            "install",
            "--dest",
            str(destination),
            "--package",
            package,
            "--json",
            *flags,
        ],
    )


@pytest.fixture
def two_providers(installer, tmp_path):
    destination = tmp_path / "skills"
    first = _install(installer, destination, "scitex-dev", "--link")
    if first.exit_code:
        pytest.fail(first.output)
    first_manifest = json.loads((destination / MANIFEST_NAME).read_text())
    second = _install(installer, destination, "scitex-io", "--no-link")
    if second.exit_code:
        pytest.fail(second.output)
    return destination, first_manifest, second


def test_partial_install_keeps_both_real_installed_providers(two_providers):
    # Arrange
    destination, _, _ = two_providers
    expected = set(list_skills(package="scitex-dev")) | set(
        list_skills(package="scitex-io")
    )
    # Act
    manifest = json.loads((destination / MANIFEST_NAME).read_text())
    # Assert
    assert {record["name"] for record in manifest["skills"]} == expected


def test_partial_install_preserves_prior_source_hash_records(two_providers):
    # Arrange
    destination, first, _ = two_providers
    old = {record["name"]: record for record in first["skills"]}
    # Act
    combined = json.loads((destination / MANIFEST_NAME).read_text())
    retained = {
        record["name"]: record for record in combined["skills"] if record["name"] in old
    }
    # Assert
    assert retained == old


def test_force_copy_overrides_editable_link_autodetection(two_providers):
    # Arrange
    destination, _, _ = two_providers
    # Act
    linked = (destination / "scitex-io").is_symlink()
    # Assert
    assert linked is False


def test_repeated_install_is_idempotent(installer, two_providers):
    # Arrange
    destination, _, _ = two_providers
    before = (destination / MANIFEST_NAME).read_bytes()
    # Act
    result = _install(installer, destination, "scitex-io", "--no-link")
    after = (destination / MANIFEST_NAME).read_bytes()
    # Assert
    assert (result.exit_code, after) == (0, before)


def test_dirty_managed_content_is_preserved(installer, two_providers):
    # Arrange
    destination, _, _ = two_providers
    note = destination / "scitex-io" / "local-note.txt"
    note.write_text("user work must survive")
    before = (destination / MANIFEST_NAME).read_bytes()
    # Act
    result = _install(installer, destination, "scitex-io", "--link", "--clean")
    # Assert
    assert (
        result.exit_code,
        note.read_text(),
        (destination / MANIFEST_NAME).read_bytes(),
    ) == (1, "user work must survive", before)


def test_foreign_namespace_is_never_removed(installer, tmp_path):
    # Arrange
    destination = tmp_path / "foreign"
    note = destination / "scitex-dev" / "notes.txt"
    note.parent.mkdir(parents=True)
    note.write_text("foreign content")
    # Act
    result = _install(installer, destination, "scitex-dev", "--link", "--clean")
    # Assert
    assert (
        result.exit_code,
        note.read_text(),
        (destination / MANIFEST_NAME).exists(),
    ) == (1, "foreign content", False)


def test_unknown_installed_package_refuses_without_creating_target(installer, tmp_path):
    # Arrange
    destination = tmp_path / "missing" / "skills"
    # Act
    result = _install(
        installer, destination, "scitex-audit-no-such-package", "--dry-run"
    )
    payload = json.loads(result.stdout)
    # Assert
    assert (result.exit_code, payload["ok"], destination.parent.exists()) == (
        2,
        False,
        False,
    )


def test_pypi_dry_run_is_unresolved_without_installed_listing(installer, tmp_path):
    # Arrange
    destination = tmp_path / "pypi" / "skills"
    # Act
    result = _install(
        installer, destination, "scitex-dev", "--source", "pypi", "--dry-run"
    )
    payload = json.loads(result.stdout)
    # Assert
    assert (
        result.exit_code,
        payload["status"],
        payload["packages"],
        payload["discovery_performed"],
        destination.parent.exists(),
    ) == (2, "not-resolved", None, False, False)


def test_real_duplicate_entry_points_refuse_as_json_before_destination_writes(
    installer, tmp_path, isolated_metadata_environment
):
    # Arrange
    site = isolated_metadata_environment
    for owner in ["audit-collision", "audit-second"]:
        dist = site / f"{owner.replace('-', '_')}-1.0.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(f"Name: {owner}\nVersion: 1.0\n")
        (dist / "entry_points.txt").write_text(
            f"[scitex_dev.skills]\naudit-collision = {owner.replace('-', '_')}\n"
        )
    destination = tmp_path / "untouched" / "skills"
    # Act
    result = _install(installer, destination, "audit-collision")
    payload = json.loads(result.stdout)
    # Assert
    assert (
        result.exit_code,
        payload["ok"],
        payload["findings"][0]["code"],
        destination.parent.exists(),
    ) == (2, False, "SI-103", False)


@pytest.fixture
def isolated_metadata_environment(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    before_path = sys.path[:]
    keys = {
        "SCITEX_DIR": str(tmp_path / "state"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "knobs.json"),
    }
    before_env = {key: os.environ.get(key) for key in keys}
    sys.path.insert(0, str(site))
    os.environ.update(keys)
    try:
        yield site
    finally:
        sys.path[:] = before_path
        for key, value in before_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
