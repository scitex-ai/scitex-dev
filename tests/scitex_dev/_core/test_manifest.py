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
    def test_read_nonexistent(self, tmp_path):
        result = read_manifest(tmp_path)
        assert result is None

    def test_read_valid(self, tmp_path):
        manifest = {"package": "test", "version": "1.0"}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))

        result = read_manifest(tmp_path)
        assert result == manifest

    def test_read_invalid_json(self, tmp_path):
        (tmp_path / "manifest.json").write_text("not json{{{")

        result = read_manifest(tmp_path)
        assert result is None


class TestWriteManifest:
    def test_write_creates_file(self, tmp_path):
        manifest = {"package": "test", "version": "1.0"}
        path = write_manifest(tmp_path, manifest)

        assert path.exists()
        with open(path) as f:
            assert json.load(f) == manifest

    def test_write_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "sub" / "dir"
        manifest = {"package": "test"}
        path = write_manifest(target, manifest)

        assert path.exists()


class TestGenerateManifest:
    def test_empty_dir(self, tmp_path):
        result = generate_manifest("test-pkg", tmp_path, version="0.1.0")

        assert result["package"] == "test-pkg"
        assert result["version"] == "0.1.0"
        assert result["pages"] == []
        assert result["formats"] == []
        assert "built_at" in result

    def test_with_html_files(self, tmp_path):
        (tmp_path / "index.html").write_text("<html></html>")
        (tmp_path / "api.html").write_text("<html></html>")

        result = generate_manifest("test-pkg", tmp_path)

        assert len(result["pages"]) == 2
        assert "html" in result["formats"]
        names = [p["name"] for p in result["pages"]]
        assert "api" in names
        assert "index" in names

    def test_nonexistent_dir(self, tmp_path):
        result = generate_manifest("test-pkg", tmp_path / "nope")
        assert result["pages"] == []
