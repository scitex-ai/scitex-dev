#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for _discovery module."""

from dataclasses import dataclass

import pytest

from scitex_dev._core.discovery import (
    discover_packages,
    get_package_root,
    get_sphinx_source,
    invalidate_cache,
)


@dataclass
class _FakeEP:
    """Tiny stand-in for ``importlib.metadata.EntryPoint``."""

    name: str
    value: str


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure discovery cache is cleared between tests."""
    invalidate_cache()
    yield
    invalidate_cache()


class TestDiscoverPackages:
    def test_discover_packages_returns_dict_mapping(self):
        # Arrange
        # Act
        # Assert
        result = discover_packages()
        assert isinstance(result, dict)

    def test_repeated_calls_return_cached_object(self):
        """Second call should return cached result."""
        # Arrange
        # Act
        # Assert
        result1 = discover_packages()
        result2 = discover_packages()
        assert result1 is result2  # Same object (cached)

    def test_invalidate_cache_forces_fresh_discovery(self):
        # Arrange
        # Act
        # Assert
        result1 = discover_packages()
        invalidate_cache()
        result2 = discover_packages()
        assert result1 is not result2  # Different objects

    def test_with_injected_entry_points(self):
        """Injected entry_points_fn + empty ecosystem yields just the EP entries."""
        # Arrange
        # Act
        # Assert
        eps = [_FakeEP(name="test-pkg", value="test_pkg")]
        result = discover_packages(
            entry_points_fn=lambda group: eps,
            ecosystem={},
        )
        assert result == {"test-pkg": "test_pkg"}

    def test_handles_entry_point_error(self):
        """Should return empty dict on error, not raise."""

        # Arrange
        # Act
        # Assert
        def _raises(group):
            raise RuntimeError("simulated entry-points failure")

        result = discover_packages(entry_points_fn=_raises, ecosystem={})
        assert result == {}


class TestGetPackageRoot:
    def test_existing_package_returns_path(self):
        # os is always available
        # Arrange
        # Act
        # Assert
        root = get_package_root("os")
        assert root is not None

    def test_nonexistent_package_returns_none(self):
        # Arrange
        # Act
        # Assert
        result = get_package_root("nonexistent_package_xyz_123")
        assert result is None

    def test_package_with_path(self):
        # Arrange
        # Act
        # Assert
        root = get_package_root("json")
        assert root is not None


class TestGetSphinxSource:
    def test_nonexistent_package_returns_none(self):
        # Arrange
        # Act
        # Assert
        result = get_sphinx_source("nonexistent_package_xyz_123")
        assert result is None

    def test_package_without_sphinx(self):
        # os module won't have sphinx docs
        # Arrange
        # Act
        # Assert
        result = get_sphinx_source("os")
        assert result is None


@pytest.fixture(params=[(layout, label, adapter) for layout in ['src', 'flat'] for label in ['plain', 'with space', 'percent%name', 'hash#name', 'café-東京', 'encoded%20literal'] for adapter in ['fast', 'public']])
def editable_uri_case(request, tmp_path):
    import json

    layout, label, adapter = request.param
    project = tmp_path / label
    module = 'owned_docs_fixture'
    package = project / ('src' if layout == 'src' else '') / module
    package.mkdir(parents=True)
    (package / '__init__.py').write_text("from pathlib import Path\nPath(__file__).with_name('imported.txt').write_text('target imported')\n")
    metadata = tmp_path / 'metadata'
    dist = metadata / 'owned_docs_fixture-0.1.dist-info'
    dist.mkdir(parents=True)
    (dist / 'METADATA').write_text('Metadata-Version: 2.1\nName: owned-docs-fixture\nVersion: 0.1\n')
    (dist / 'direct_url.json').write_text(json.dumps({'url': project.as_uri(), 'dir_info': {'editable': True}}))
    protected = [package / '__init__.py', dist / 'METADATA', dist / 'direct_url.json']
    before = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in protected]
    yield adapter, metadata, package, module, protected, before


def test_editable_file_uri_roots_are_decoded_without_importing_target(editable_uri_case):
    import json
    import subprocess
    import sys

    # Arrange
    adapter, metadata, package, module, protected, before = editable_uri_case
    code = """
from pathlib import Path
import json,sys
from scitex_dev._core.discovery import _get_package_root_fast,get_package_root
metadata,package,module,adapter=sys.argv[1:];package=Path(package)
sys.path[:0]=[metadata,str(package.parent)]
root=(_get_package_root_fast if adapter=='fast' else get_package_root)(module)
print(json.dumps({'root':str(root) if root is not None else None,'imported':(package/'imported.txt').exists(),'loaded':module in sys.modules}))
"""
    # Act
    completed = subprocess.run([sys.executable, '-I', '-c', code, str(metadata), str(package), module, adapter], cwd=metadata.parent, capture_output=True, check=True, timeout=15)
    outcome = json.loads(completed.stdout)
    after = [(f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) for f in protected]
    # Assert
    assert (outcome, after) == ({'root': str(package), 'imported': False, 'loaded': False}, before)
