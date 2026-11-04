"""Owned installed metadata for shared skill adapter identity controls."""

import os
import sys

import pytest


@pytest.fixture
def colliding_skill_providers(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    marker = tmp_path / "imported-consumer"
    namespace = "scitex-adapter-shared"
    for owner, module, content in (
        ("scitex-adapter-current", "adapter_current", "# Current owner\n"),
        ("scitex-adapter-archived", "adapter_archived", "# Archived owner\n"),
    ):
        root = site / module
        resources = root / "_skills" / namespace
        resources.mkdir(parents=True)
        (resources / "SKILL.md").write_text(content)
        (root / "__init__.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
            "raise RuntimeError('consumer must not import')\n"
        )
        metadata = site / f"{owner.replace('-', '_')}-1.0.dist-info"
        metadata.mkdir()
        (metadata / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {owner}\nVersion: 1.0\n"
        )
        (metadata / "entry_points.txt").write_text(
            f"[scitex_dev.skills]\n{namespace} = {module}\n"
        )
    before_path = sys.path[:]
    environment = {
        "SCITEX_DIR": str(tmp_path / "state"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "knobs.json"),
    }
    before_environment = {key: os.environ.get(key) for key in environment}
    sys.path.insert(0, str(site))
    os.environ.update(environment)
    try:
        yield namespace, marker
    finally:
        sys.path[:] = before_path
        for key, value in before_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
