#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for _manifest module."""

import json


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
