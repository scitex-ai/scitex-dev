"""Real filesystem controls for projection commit and concurrent-change detection."""

import json
import os
import sys
from functools import partial

import pytest

from scitex_dev._core.config import set_package_knob
from scitex_dev._ecosystem._skills.installed_providers import discover_skill_packages
from scitex_dev._ecosystem._skills.transaction import install_projection
from scitex_dev.skill_registry import MANIFEST_NAME


from scitex_dev._ecosystem._skills.transaction import (
    _locked_store,
    _promote_projection,
    _snapshot,
)


def test_real_filesystem_promotion_failure_restores_original(tmp_path):
    # Arrange
    target = tmp_path / "target"
    target.mkdir()
    original = target / "original.txt"
    original.write_text("keep original")
    missing_stage = tmp_path / "missing-stage"
    backup = tmp_path / "backup"
    # Act
    try:
        _promote_projection(missing_stage, target, backup)
        failure = None
    except FileNotFoundError as error:
        failure = type(error).__name__
    # Assert
    assert (failure, original.read_text(), backup.exists()) == (
        "FileNotFoundError",
        "keep original",
        False,
    )


def test_snapshot_observes_changed_content_behind_namespace_symlink(tmp_path):
    # Arrange
    source = tmp_path / "source"
    source.mkdir()
    document = source / "SKILL.md"
    document.write_text("before")
    target = tmp_path / "store"
    target.mkdir()
    (target / "example").symlink_to(source, target_is_directory=True)
    before = _snapshot(target)
    # Act
    document.write_text("after")
    after = _snapshot(target)
    # Assert
    assert after != before


def test_lock_symlink_refuses_without_touching_foreign_file(tmp_path):
    # Arrange
    foreign = tmp_path / "foreign.txt"
    foreign.write_text("foreign content")
    before_mode = foreign.stat().st_mode
    target = tmp_path / "skills"
    (tmp_path / ".skills.skills-install.lock").symlink_to(foreign)
    entered = False
    # Act
    try:
        with _locked_store(target):
            entered = True
    except (OSError, ValueError):
        pass
    # Assert
    assert (entered, foreign.read_text(), foreign.stat().st_mode) == (
        False,
        "foreign content",
        before_mode,
    )


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


@pytest.fixture
def real_installed_store(tmp_path, isolated_metadata_environment):
    site = isolated_metadata_environment
    for owner in ["audit-first", "audit-second"]:
        module = owner.replace("-", "_")
        skill = site / module / "_skills" / owner
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"---\nname: {owner}\n---\n# {owner}\n")
        extra = skill.parent / f"{owner}-extra"
        extra.mkdir()
        (extra / "SKILL.md").write_text(f"# {owner} extra\n")
        dist = site / f"{module}-1.0.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(f"Name: {owner}\nVersion: 1.0\n")
        (dist / "entry_points.txt").write_text(
            f"[scitex_dev.skills]\n{owner} = {module}\n"
        )
    dest = tmp_path / "store"
    discover = partial(discover_skill_packages, path=[site])
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    if not result.audit.ok:
        pytest.fail(str(result.audit.issues))
    return site, dest, discover


def test_full_refresh_removes_disabled_managed_owner_and_extras(real_installed_store):
    # Arrange
    _, dest, discover = real_installed_store
    set_package_knob("audit-first", "skills", False)
    # Act
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    records = json.loads((dest / MANIFEST_NAME).read_text())["skills"]
    # Assert
    assert (
        result.audit.ok,
        {item["owner"] for item in records},
        (dest / "audit-first").exists(),
    ) == (True, {"audit-second"}, False)


def test_full_refresh_removes_uninstalled_managed_owner(real_installed_store):
    # Arrange
    site, dest, discover = real_installed_store
    (site / "audit_first-1.0.dist-info").rename(site / "uninstalled-metadata")
    import shutil

    shutil.rmtree(site / "audit_first")
    # Act
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    # Assert
    assert (
        result.audit.ok,
        (dest / "audit-first").exists(),
        (dest / "audit-first-extra").exists(),
    ) == (True, False, False)


def test_partial_refresh_prunes_selected_extra_but_preserves_other_owner(
    real_installed_store,
):
    # Arrange
    site, dest, discover = real_installed_store
    extra = site / "audit_first" / "_skills" / "audit-first-extra"
    (extra / "SKILL.md").unlink()
    extra.rmdir()
    # Act
    result, _ = install_projection(
        dest, package="audit-first", force_copy=True, _discover_fn=discover
    )
    records = json.loads((dest / MANIFEST_NAME).read_text())["skills"]
    # Assert
    assert (
        result.audit.ok,
        {item["name"] for item in records},
        (dest / "audit-first-extra").exists(),
    ) == (True, {"audit-first", "audit-second", "audit-second-extra"}, False)


def test_full_refresh_can_reconcile_to_no_enabled_providers(real_installed_store):
    # Arrange
    _, dest, discover = real_installed_store
    for owner in ["audit-first", "audit-second"]:
        set_package_knob(owner, "skills", False)
    # Act
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    # Assert
    assert (
        result.audit.ok,
        json.loads((dest / MANIFEST_NAME).read_text())["skills"],
        (dest / "SKILL.md").exists(),
    ) == (True, [], False)


def test_cross_owner_partial_install_refuses_without_changing_store(
    real_installed_store,
):
    # Arrange
    site, dest, discover = real_installed_store
    before = (dest / MANIFEST_NAME).read_bytes()
    payload = (dest / "audit-first-extra" / "SKILL.md").read_bytes()
    root = site / "audit_third" / "_skills" / "audit-first-extra"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("# Different owner's collision\n")
    dist = site / "audit_third-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: audit-third\nVersion: 1.0\n")
    (dist / "entry_points.txt").write_text(
        "[scitex_dev.skills]\naudit-third = audit_third\n"
    )
    # Act
    result, _ = install_projection(
        dest, package="audit-third", force_copy=True, _discover_fn=discover
    )
    # Assert
    assert (
        result.audit.ok,
        [issue.code for issue in result.audit.issues],
        (dest / MANIFEST_NAME).read_bytes(),
        (dest / "audit-first-extra" / "SKILL.md").read_bytes(),
    ) == (False, ["SI-201"], before, payload)


def test_full_reconcile_refuses_dirty_disabled_owner_without_deleting_content(
    real_installed_store,
):
    # Arrange
    _, dest, discover = real_installed_store
    note = dest / "audit-first" / "user-note.txt"
    note.write_text("must survive")
    before = (dest / MANIFEST_NAME).read_bytes()
    set_package_knob("audit-first", "skills", False)
    # Act
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    # Assert
    assert (result.audit.ok, note.read_text(), (dest / MANIFEST_NAME).read_bytes()) == (
        False,
        "must survive",
        before,
    )


def test_legacy_namespace_owner_upgrades_only_for_identical_canonical_source(
    real_installed_store,
):
    # Arrange
    from dataclasses import replace

    from scitex_dev._ecosystem._skills.transaction import _existing_registry
    from scitex_dev.skill_registry import write_projection_manifest

    _, dest, discover = real_installed_store
    records = _existing_registry(dest).records
    legacy = tuple(replace(item, owner=item.name) for item in records)
    write_projection_manifest(legacy, "scitex-dev", dest)
    # Act
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    document = json.loads((dest / MANIFEST_NAME).read_text())
    # Assert
    assert (
        result.audit.ok,
        {item["name"]: item["owner"] for item in document["skills"]},
    ) == (
        True,
        {
            "audit-first": "audit-first",
            "audit-first-extra": "audit-first",
            "audit-second": "audit-second",
            "audit-second-extra": "audit-second",
        },
    )


def test_legacy_namespace_owner_cannot_adopt_another_source(real_installed_store):
    # Arrange
    from dataclasses import replace

    from scitex_dev._ecosystem._skills.transaction import _existing_registry
    from scitex_dev.skill_registry import write_projection_manifest

    site, dest, discover = real_installed_store
    records = _existing_registry(dest).records
    write_projection_manifest(
        tuple(replace(item, owner=item.name) for item in records), "scitex-dev", dest
    )
    before = (dest / MANIFEST_NAME).read_bytes()
    old = site / "audit_first" / "_skills" / "audit-first-extra"
    (old / "SKILL.md").unlink()
    old.rmdir()
    replacement = site / "audit_second" / "_skills" / "audit-first-extra"
    replacement.mkdir()
    (replacement / "SKILL.md").write_text("# Unrelated provider\n")
    # Act
    result, _ = install_projection(dest, force_copy=True, _discover_fn=discover)
    # Assert
    assert (
        result.audit.ok,
        [issue.code for issue in result.audit.issues],
        (dest / MANIFEST_NAME).read_bytes(),
    ) == (False, ["SI-201"], before)
