#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for _manifest module."""

import json

import pytest


from scitex_dev._core.manifest import (
    generate_manifest,
    read_manifest,
    write_manifest,
)


class TestReadManifest:
    def test_read_nonexistent_returns_none(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = read_manifest(tmp_path)
        assert result is None

    def test_read_valid_manifest_returns_dict(self, tmp_path):
        # Arrange
        # Act
        # Assert
        manifest = {"package": "test", "version": "1.0"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        result = read_manifest(tmp_path)
        assert result == manifest

    def test_read_invalid_json(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "manifest.json").write_text("not json{{{")

        result = read_manifest(tmp_path)
        assert result is None


class TestWriteManifest:
    def test_write_creates_file_at_returned_path(self, tmp_path):
        # Arrange
        manifest = {"package": "test", "version": "1.0"}
        # Act
        path = write_manifest(tmp_path, manifest)
        # Assert
        assert path.exists()

    def test_write_file_contents_roundtrip_to_input_manifest(self, tmp_path):
        # Arrange
        manifest = {"package": "test", "version": "1.0"}
        # Act
        path = write_manifest(tmp_path, manifest)
        with open(path) as f:
            loaded = json.load(f)
        # Assert
        assert loaded == manifest

    def test_write_creates_parent_dirs(self, tmp_path):
        # Arrange
        # Act
        # Assert
        target = tmp_path / "sub" / "dir"
        manifest = {"package": "test"}
        path = write_manifest(target, manifest)

        assert path.exists()


class TestGenerateManifest:
    def test_empty_dir_yields_no_pages_or_formats_result_package_test_pkg(
        self, tmp_path
    ):
        # Arrange
        # Act
        # Assert
        result = generate_manifest("test-pkg", tmp_path, version="0.1.0")

        assert result["package"] == "test-pkg"

    def test_empty_dir_yields_no_pages_or_formats_result_version_0_1_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = generate_manifest("test-pkg", tmp_path, version="0.1.0")

        assert result["version"] == "0.1.0"

    def test_empty_dir_yields_no_pages_or_formats_result_pages(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = generate_manifest("test-pkg", tmp_path, version="0.1.0")

        assert result["pages"] == []

    def test_empty_dir_yields_no_pages_or_formats_result_formats(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = generate_manifest("test-pkg", tmp_path, version="0.1.0")

        assert result["formats"] == []

    def test_empty_dir_yields_no_pages_or_formats_built_at_in_result(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = generate_manifest("test-pkg", tmp_path, version="0.1.0")

        assert "built_at" in result

    def test_with_html_files_len_result_pages_2(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "api.html").write_text("<html></html>")

        result = generate_manifest("test-pkg", tmp_path)

        assert len(result["pages"]) == 2
        names = [p["name"] for p in result["pages"]]

    def test_with_html_files_html_in_result_formats(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "api.html").write_text("<html></html>")

        result = generate_manifest("test-pkg", tmp_path)

        assert "html" in result["formats"]
        names = [p["name"] for p in result["pages"]]

    def test_with_html_files_api_in_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "api.html").write_text("<html></html>")

        result = generate_manifest("test-pkg", tmp_path)

        names = [p["name"] for p in result["pages"]]
        assert "api" in names

    def test_with_html_files_index_in_names(self, tmp_path):
        # Arrange
        # Act
        # Assert
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "api.html").write_text("<html></html>")

        result = generate_manifest("test-pkg", tmp_path)

        names = [p["name"] for p in result["pages"]]
        assert "index" in names

    def test_nonexistent_dir_yields_empty_pages(self, tmp_path):
        # Arrange
        # Act
        # Assert
        result = generate_manifest("test-pkg", tmp_path / "nope")
        assert result["pages"] == []


@pytest.mark.parametrize(
    ("asset", "expected"),
    [
        ("objects.inv", ["html"]),
        ("manifest.json", ["html"]),
        ("globalcontext.json", ["html"]),
        ("api.fjson", ["html", "json"]),
        ("api.json", ["html", "json"]),
        ("other.json", ["html"]),
        ("nested/api.fjson", ["html", "json"]),
    ],
)
def test_formats_follow_page_assets_instead_of_inventory(tmp_path, asset, expected):
    # Arrange
    (tmp_path / "api.html").write_text("<h1>API</h1>")
    target = tmp_path / asset
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"body": "<h1>API</h1>", "title": "API"}))
    # Act
    result = generate_manifest("owned-docs", tmp_path)
    # Assert
    assert result["formats"] == expected


def test_directory_named_like_json_page_does_not_advertise_format(tmp_path):
    # Arrange
    (tmp_path / "api.html").write_text("<h1>API</h1>")
    (tmp_path / "api.fjson").mkdir()
    (tmp_path / "api.json").mkdir()
    # Act
    result = generate_manifest("owned-docs", tmp_path)
    # Assert
    assert result["formats"] == ["html"]


def test_json_builder_page_without_html_advertises_json(tmp_path):
    # Arrange
    (tmp_path / "index.fjson").write_text(json.dumps({"body": "Page body"}))
    # Act
    result = generate_manifest("owned-docs", tmp_path)
    # Assert
    assert result["formats"] == ["json"]


@pytest.mark.parametrize("name", ["manifest", "globalcontext", "searchindex"])
def test_control_json_is_not_a_page_sidecar(tmp_path, name):
    # Arrange
    (tmp_path / f"{name}.html").write_text("<h1>Documentation</h1>")
    (tmp_path / f"{name}.json").write_text(json.dumps({"metadata": "not a page"}))
    # Act
    result = generate_manifest("owned-docs", tmp_path)
    # Assert
    assert result["formats"] == ["html"]


def test_manifest_link_outside_docs_is_not_read(tmp_path):
    # Arrange
    docs = tmp_path / "docs"
    docs.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"package": "outside-sentinel"}))
    (docs / "manifest.json").symlink_to(outside)
    # Act
    result = read_manifest(docs)
    # Assert
    assert result is None


def test_manifest_link_inside_docs_remains_readable(tmp_path):
    # Arrange
    target = tmp_path / "metadata.json"
    expected = {"package": "inside-sentinel", "pages": []}
    target.write_text(json.dumps(expected))
    (tmp_path / "manifest.json").symlink_to(target)
    # Act
    result = read_manifest(tmp_path)
    # Assert
    assert result == expected


@pytest.mark.parametrize("suffix", [".html", ".fjson", ".json"])
def test_external_assets_are_not_manifest_pages_or_formats(tmp_path, suffix):
    # Arrange
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "owned.html").write_text("<h1>Owned</h1>")
    outside = tmp_path / ("outside" + suffix)
    outside.write_text(json.dumps({"body": "Outside sentinel"}))
    name = "owned.json" if suffix == ".json" else "alias" + suffix
    (docs / name).symlink_to(outside)
    # Act
    result = generate_manifest("owned-docs", docs)
    # Assert
    assert (result["pages"], result["formats"]) == (
        [{"name": "owned", "title": "Owned", "path": "owned.html"}], ["html"]
    )


@pytest.mark.parametrize("suffix", [".html", ".fjson", ".json"])
def test_directory_assets_are_not_manifest_pages_or_formats(tmp_path, suffix):
    # Arrange
    (tmp_path / "owned.html").write_text("<h1>Owned</h1>")
    name = "owned.json" if suffix == ".json" else "directory" + suffix
    (tmp_path / name).mkdir()
    # Act
    result = generate_manifest("owned-docs", tmp_path)
    # Assert
    assert (result["pages"], result["formats"]) == (
        [{"name": "owned", "title": "Owned", "path": "owned.html"}], ["html"]
    )


@pytest.mark.parametrize("asset,formats,names", [
    ("alias.html", ["html"], ["alias", "owned"]),
    ("alias.fjson", ["html", "json"], ["owned"]),
    ("owned.json", ["html", "json"], ["owned"]),
])
def test_internal_asset_links_remain_available(tmp_path, asset, formats, names):
    # Arrange
    (tmp_path / "owned.html").write_text("<h1>Owned</h1>")
    target = tmp_path / "payload"
    target.write_text(json.dumps({"body": "Inside sentinel"}))
    (tmp_path / asset).symlink_to(target)
    # Act
    result = generate_manifest("owned-docs", tmp_path)
    # Assert
    assert ([page["name"] for page in result["pages"]], result["formats"]) == (
        names, formats
    )


def test_public_overview_regenerates_from_safe_assets_after_external_manifest(tmp_path):
    # Arrange
    from scitex_dev import get_docs

    docs = tmp_path / "package" / "_sphinx_html"
    docs.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({"pages": [{"name": "outside-sentinel"}]}))
    (docs / "manifest.json").symlink_to(outside)
    (docs / "owned.html").write_text("<h1>Owned</h1>")
    # Act
    result = get_docs(
        package="owned-docs", _discover_fn=lambda: {"owned-docs": "json"},
        _root_fn=lambda _module: docs.parent, _sphinx_fn=lambda _module: None,
    )
    # Assert
    assert result["pages"] == [{"name": "owned", "title": "Owned", "path": "owned.html"}]


def _write_error(docs, payload):
    """Observe write refusal alongside file preservation in owned fixtures."""
    try:
        write_manifest(docs, payload)
    except ValueError as error:
        return error
    return None


def _linked_manifest(tmp_path, existing):
    """Create an existing or dangling target outside the selected docs root."""
    docs = tmp_path / "docs"
    docs.mkdir()
    outside = tmp_path / "outside.json"
    if existing:
        outside.write_bytes(b"Outside sentinel, preserve exactly.\n")
    (docs / "manifest.json").symlink_to(outside)
    return docs, outside


@pytest.mark.parametrize("existing", [True, False])
def test_manifest_write_refuses_external_link_without_changing_target(tmp_path, existing):
    # Arrange
    docs, outside = _linked_manifest(tmp_path, existing)
    expected_bytes = b"Outside sentinel, preserve exactly.\n" if existing else None
    # Act
    error = _write_error(docs, {"package": "owned"})
    # Assert
    assert (
        isinstance(error, ValueError), outside.exists(),
        outside.read_bytes() if outside.exists() else None,
        (docs / "manifest.json").is_symlink(),
    ) == (True, existing, expected_bytes, True)


def _internal_manifest_link(tmp_path, existing):
    """Keep internal links valid for both existing and not-yet-created files."""
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "metadata.json"
    if existing:
        target.write_bytes(b"Old metadata\n")
    (docs / "manifest.json").symlink_to(target)
    return docs, target


@pytest.mark.parametrize("existing", [True, False])
def test_manifest_write_preserves_internal_link_behavior(tmp_path, existing):
    # Arrange
    docs, target = _internal_manifest_link(tmp_path, existing)
    payload = {"package": "owned", "pages": []}
    # Act
    result = write_manifest(docs, payload)
    # Assert
    assert (result, json.loads(target.read_text()), result.is_symlink()) == (
        docs / "manifest.json", payload, True
    )


def test_manifest_write_accepts_explicit_symlinked_docs_root(tmp_path):
    # Arrange
    real = tmp_path / "real-docs"
    real.mkdir()
    alias = tmp_path / "docs-alias"
    alias.symlink_to(real, target_is_directory=True)
    payload = {"package": "owned"}
    # Act
    path = write_manifest(alias, payload)
    # Assert
    assert (path, json.loads((real / "manifest.json").read_text())) == (
        alias / "manifest.json", payload
    )
