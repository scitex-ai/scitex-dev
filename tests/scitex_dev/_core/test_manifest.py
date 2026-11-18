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
