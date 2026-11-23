"""Non-object manifests must preserve safe discovery and valid object contents."""

import json

import pytest

from scitex_dev._core.manifest import read_manifest


@pytest.mark.parametrize("value", [[], ["unexpected"], "unexpected", 23, False, None])
def test_nonobject_json_manifest_is_unavailable(tmp_path, value):
    # Arrange
    (tmp_path / "manifest.json").write_text(json.dumps(value))
    # Act
    result = read_manifest(tmp_path)
    # Assert
    assert result is None


@pytest.mark.parametrize("value", [{}, {"package": "legacy"}, {"pages": [], "custom": "kept"}])
def test_manifest_objects_preserve_legacy_and_custom_fields(tmp_path, value):
    # Arrange
    (tmp_path / "manifest.json").write_text(json.dumps(value))
    # Act
    result = read_manifest(tmp_path)
    # Assert
    assert result == value


@pytest.mark.parametrize("value", [[], 23, "unexpected", False])
def test_public_overview_regenerates_after_nonobject_manifest(tmp_path, value):
    # Arrange
    from scitex_dev import get_docs

    docs = tmp_path / "package" / "_sphinx_html"
    docs.mkdir(parents=True)
    (docs / "manifest.json").write_text(json.dumps(value))
    (docs / "owned.html").write_text("<h1>Owned</h1>")
    # Act
    result = get_docs(
        package="owned-docs", _discover_fn=lambda: {"owned-docs": "json"},
        _root_fn=lambda _module: docs.parent, _sphinx_fn=lambda _module: None,
    )
    # Assert
    assert isinstance(result, dict) and result["pages"] == [
        {"name": "owned", "title": "Owned", "path": "owned.html"}
    ]
