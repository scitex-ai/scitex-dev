"""Public installed registry reads real leaf metadata without harness writes."""

import os
import sys

import pytest

from scitex_dev._core.config import set_package_knob
from scitex_dev.skill_registry import SkillRegistryError, discover_installed_skills


@pytest.fixture
def installed_leaf(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    owner = "audit-installed-read"
    names = [owner, "audit-installed-extra"]
    module = site / "audit_installed_read"
    module.mkdir()
    marker = tmp_path / "consumer-imported"
    (module / "__init__.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\nraise RuntimeError('not a discovery import')\n"
    )
    for name in names:
        resource = module / "_skills" / name
        resource.mkdir(parents=True)
        (resource / "SKILL.md").write_text(f"# {name}\n")
    dist = site / "audit_installed_read-1.0.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Name: {owner}\nVersion: 1.0\n")
    (dist / "entry_points.txt").write_text(
        "[scitex_dev.skills]\n"
        + "".join(f"{name} = audit_installed_read\n" for name in names)
    )
    before_path = sys.path[:]
    keys = {
        "SCITEX_DIR": str(tmp_path / "state"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "knobs.json"),
    }
    before_env = {key: os.environ.get(key) for key in keys}
    sys.path.insert(0, str(site))
    os.environ.update(keys)
    try:
        yield site, owner, names, marker, dist
    finally:
        sys.path[:] = before_path
        for key, value in before_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_public_registry_preserves_distribution_owner_for_all_aliases(installed_leaf):
    # Arrange
    _, owner, names, marker, _ = installed_leaf
    # Act
    report = discover_installed_skills(package=owner)
    # Assert
    assert (
        report.ok,
        {record.name: record.owner for record in report.require_valid()},
        marker.exists(),
    ) == (True, {name: owner for name in names}, False)


def test_disabled_provider_is_valid_empty_read_not_successful_install(installed_leaf):
    # Arrange
    _, owner, _, marker, _ = installed_leaf
    set_package_knob(owner, "skills", False)
    # Act
    report = discover_installed_skills(package=owner)
    # Assert
    assert (report.ok, report.require_valid(), marker.exists()) == (True, (), False)


def test_public_registry_refuses_same_namespace_from_distinct_resource_roots(
    installed_leaf,
):
    # Arrange
    site, owner, _, _, dist = installed_leaf
    extra = site / "audit_second_root" / "_skills" / "audit-installed-extra"
    extra.mkdir(parents=True)
    (extra / "SKILL.md").write_text("# Different canonical source\n")
    with (dist / "entry_points.txt").open("a") as handle:
        handle.write("audit-second-alias = audit_second_root\n")
    # Act
    # Assert
    with pytest.raises(SkillRegistryError, match="duplicate skill namespace"):
        discover_installed_skills(package=owner)
