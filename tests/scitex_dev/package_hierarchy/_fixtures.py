"""Real metadata and resources exercise the inert navigation contract."""

import copy
import json
import sys
from importlib import invalidate_caches

import pytest

from scitex_dev.package_hierarchy import list_package_hierarchies, validate_package_hierarchy


@pytest.fixture
def import_path():
    paths = []
    def add(root):
        path = str(root)
        sys.path.insert(0, path)
        paths.append(path)
        invalidate_caches()
    yield add
    for path in paths:
        sys.path.remove(path)
    invalidate_caches()


def _catalog():
    return {"schema_version": 1, "root": "example", "nodes": [
        {"id": "example", "label": "Example", "index": "0", "parent_id": None, "kind": "root"},
        {"id": "apps", "label": "Apps", "index": "1", "parent_id": "example", "kind": "group"},
        {"id": "package:example-leaf", "label": "Leaf", "index": "1.2", "parent_id": "apps", "kind": "package", "distribution": "example-leaf"},
    ]}


def _provider(root, *, owner="owned-example", target="inert_hierarchy_fixture"):
    info = root / (owner.replace("-", "_") + "-1.0.dist-info")
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {owner}\nVersion: 1.0\n")
    (info / "entry_points.txt").write_text(f"[scitex_dev.hierarchy]\nexample = {target}\n")
    package = root / target
    if not package.exists():
        package.mkdir()
        (package / "__init__.py").write_text("raise RuntimeError('provider code must never execute')\n")
        (package / "_package_hierarchy.json").write_text(json.dumps(_catalog()))
    return package


