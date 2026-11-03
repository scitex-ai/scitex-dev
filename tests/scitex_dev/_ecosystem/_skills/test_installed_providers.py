"""Real installed metadata controls for provider identity and opt-out policy."""

import os
import sys
from functools import partial

import pytest

from scitex_dev._core.config import set_package_knob
from scitex_dev._ecosystem._skills.installed_providers import discover_skill_packages
from scitex_dev._ecosystem._skills.skills import list_skills
from scitex_dev.skill_registry import SkillRegistryError


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
def installed_provider(tmp_path, isolated_metadata_environment):
    site = isolated_metadata_environment
    owner = "scitex-audit-leaf"
    module = "unrelated_module.nested"
    root = site / "unrelated_module" / "nested"
    root.mkdir(parents=True)
    marker = tmp_path / "consumer-imported"
    for package in [root.parent, root]:
        (package / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            "raise RuntimeError('consumer must never import')\n"
        )
    skill = root / "_skills" / owner
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"---\nname: {owner}\n---\n# Example\n")
    dist = site / "scitex_audit_leaf-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {owner}\nVersion: 1.0\n"
    )
    (dist / "entry_points.txt").write_text(f"[scitex_dev.skills]\n{owner} = {module}\n")
    return site, owner, root, marker, dist


def test_skills_only_nested_provider_uses_owning_distribution_without_import(
    installed_provider,
):
    # Arrange
    site, owner, root, marker, _ = installed_provider
    # Act
    listed = list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))
    # Assert
    assert (listed[owner][0]["owner"], listed[owner][0]["path"], marker.exists()) == (
        owner,
        str(root / "_skills" / owner / "SKILL.md"),
        False,
    )


def test_real_opt_out_excludes_all_namespaces_owned_by_provider(installed_provider):
    # Arrange
    site, owner, root, _, _ = installed_provider
    extra = root / "_skills" / "audit-extra"
    extra.mkdir()
    (extra / "SKILL.md").write_text("# Extra\n")
    set_package_knob(owner, "skills", False)
    # Act
    listed = list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))
    # Assert
    assert listed == {}


def test_duplicate_owned_namespace_refuses_instead_of_last_wins(installed_provider):
    # Arrange
    site, owner, _, _, _ = installed_provider
    other = site / "second_module"
    (other / "_skills" / owner).mkdir(parents=True)
    (other / "_skills" / owner / "SKILL.md").write_text("# Collision\n")
    dist = site / "scitex_audit_second-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: scitex-audit-second\nVersion: 1.0\n")
    (dist / "entry_points.txt").write_text(
        "[scitex_dev.skills]\nscitex-audit-second = second_module\n"
    )
    # Act
    # Assert
    with pytest.raises(SkillRegistryError, match="duplicate skill namespace"):
        list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))


def test_editable_nested_provider_resolves_encoded_source_path_without_import(
    installed_provider, tmp_path
):
    # Arrange
    import json

    site, owner, root, marker, dist = installed_provider
    checkout = tmp_path / "editable source"
    destination = checkout / "src" / "unrelated_module" / "nested"
    destination.parent.mkdir(parents=True)
    root.rename(destination)
    (dist / "direct_url.json").write_text(
        json.dumps({"url": checkout.as_uri(), "dir_info": {"editable": True}})
    )
    # Act
    listed = list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))
    # Assert
    assert (listed[owner][0]["path"], marker.exists()) == (
        str(destination / "_skills" / owner / "SKILL.md"),
        False,
    )


def test_distribution_can_own_multiple_declared_skill_namespaces(installed_provider):
    # Arrange
    site, owner, _, marker, dist = installed_provider
    extra = site / "secondary_target" / "_skills" / "audit-secondary"
    extra.mkdir(parents=True)
    (extra / "SKILL.md").write_text("# Secondary\n")
    with (dist / "entry_points.txt").open("a") as handle:
        handle.write("audit-secondary = secondary_target\n")
    # Act
    listed = list_skills(
        package=owner, _discover_fn=partial(discover_skill_packages, path=[site])
    )
    # Assert
    assert (
        {name: entries[0]["owner"] for name, entries in listed.items()},
        marker.exists(),
    ) == ({owner: owner, "audit-secondary": owner}, False)


def test_opted_out_owner_does_not_block_an_enabled_same_namespace_provider(
    installed_provider,
):
    # Arrange
    site, owner, _, _, _ = installed_provider
    dist = site / "audit_disabled-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: audit-disabled\nVersion: 1.0\n")
    (dist / "entry_points.txt").write_text(
        f"[scitex_dev.skills]\n{owner} = missing_disabled_module\n"
    )
    set_package_knob("audit-disabled", "skills", False)
    # Act
    listed = list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))
    # Assert
    assert {name: entries[0]["owner"] for name, entries in listed.items()} == {
        owner: owner
    }


def test_distribution_selector_uses_shared_pep503_normalization(installed_provider):
    # Arrange
    site, owner, _, _, _ = installed_provider
    # Act
    listed = list_skills(
        package="SCITEX_AUDIT_LEAF",
        _discover_fn=partial(discover_skill_packages, path=[site]),
    )
    # Assert
    assert list(listed) == [owner]


@pytest.mark.parametrize(
    "directory_info", [{}, {"editable": False}, {"editable": "true"}]
)
def test_noneditable_direct_url_keeps_installed_resources_authoritative(
    installed_provider, tmp_path, directory_info
):
    # Arrange
    import json

    site, owner, root, marker, dist = installed_provider
    checkout = tmp_path / "uninstalled checkout"
    source = checkout / "src" / "unrelated_module" / "nested" / "_skills" / owner
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "# Uninstalled source must not shadow installed resources\n"
    )
    (dist / "direct_url.json").write_text(
        json.dumps({"url": checkout.as_uri(), "dir_info": directory_info})
    )
    # Act
    listed = list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))
    # Assert
    assert (listed[owner][0]["path"], marker.exists()) == (
        str(root / "_skills" / owner / "SKILL.md"),
        False,
    )


@pytest.mark.parametrize(
    "target",
    [
        "unrelated_module.nested:factory",
        "../outside",
        "/absolute/module",
        "unrelated_module..nested",
        r"unrelated_module\nested",
    ],
)
def test_unsupported_module_identity_refuses_before_consumer_import(
    installed_provider, target
):
    # Arrange
    from scitex_dev._ecosystem._skills.installed_providers import get_skill_package_root

    _, owner, _, _, _ = installed_provider
    # Act
    # Assert
    with pytest.raises(SkillRegistryError, match="unsupported skill module target"):
        get_skill_package_root(owner, target)


def test_factory_entry_point_is_not_silently_reinterpreted_as_module_resources(
    installed_provider,
):
    # Arrange
    site, owner, _, _, dist = installed_provider
    (dist / "entry_points.txt").write_text(
        f"[scitex_dev.skills]\n{owner} = unrelated_module.nested:factory\n"
    )
    # Act
    # Assert
    with pytest.raises(SkillRegistryError, match="unsupported skill module target"):
        list_skills(_discover_fn=partial(discover_skill_packages, path=[site]))
