#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the main docs module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scitex_dev._discovery import invalidate_cache
from scitex_dev.docs import build_docs, get_docs, search_docs


@pytest.fixture(autouse=True)
def clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


class TestGetDocs:
    def test_mutual_exclusion(self):
        """Cannot use both package= and packages=."""
        with pytest.raises(ValueError, match="singular.*plural"):
            get_docs(package="a", packages=["b"])

    def test_no_packages_discovered(self):
        """With no entry points, returns empty dict."""
        with patch("scitex_dev.docs.discover_packages", return_value={}):
            result = get_docs()
        assert result == {}

    def test_single_package_not_found(self):
        with patch("scitex_dev.docs.discover_packages", return_value={}):
            with pytest.raises(LookupError, match="not found"):
                get_docs(package="nonexistent")

    def test_single_package_introspect_fallback(self):
        """When no built docs exist, falls back to introspection."""
        with patch(
            "scitex_dev.docs.discover_packages",
            return_value={"test-pkg": "json"},
        ):
            with patch(
                "scitex_dev.docs.get_package_root",
                return_value=None,
            ):
                with patch(
                    "scitex_dev.docs.get_sphinx_source",
                    return_value=None,
                ):
                    result = get_docs(package="test-pkg")

        # Should return introspected docs for the json module
        assert isinstance(result, dict)
        assert "json" in result.get("package", "")

    def test_single_package_html_format(self, tmp_path):
        """HTML format returns a Path."""
        html_dir = tmp_path / "_sphinx_html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html></html>")

        with patch(
            "scitex_dev.docs.discover_packages",
            return_value={"test-pkg": "test_mod"},
        ):
            with patch(
                "scitex_dev.docs.get_package_root",
                return_value=tmp_path,
            ):
                result = get_docs(package="test-pkg", format="html")

        assert isinstance(result, Path)
        assert result == html_dir

    def test_multiple_packages(self):
        with patch(
            "scitex_dev.docs.discover_packages",
            return_value={"pkg-a": "json", "pkg-b": "os"},
        ):
            with patch("scitex_dev.docs.get_package_root", return_value=None):
                with patch("scitex_dev.docs.get_sphinx_source", return_value=None):
                    result = get_docs(packages=["pkg-a", "pkg-b"])

        assert isinstance(result, dict)
        assert "pkg-a" in result
        assert "pkg-b" in result

    def test_unknown_format(self, tmp_path):
        html_dir = tmp_path / "_sphinx_html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html></html>")

        with patch(
            "scitex_dev.docs.discover_packages",
            return_value={"test-pkg": "test_mod"},
        ):
            with patch(
                "scitex_dev.docs.get_package_root",
                return_value=tmp_path,
            ):
                with pytest.raises(ValueError, match="Unknown format"):
                    get_docs(package="test-pkg", format="pdf")


class TestSearchDocs:
    def test_search_empty(self):
        with patch("scitex_dev.docs.discover_packages", return_value={}):
            result = search_docs(query="anything")
        assert result == []

    def test_search_finds_pages(self):
        manifest = {
            "pages": [
                {"name": "api", "title": "API Reference"},
                {"name": "tutorial", "title": "Getting Started Tutorial"},
            ],
            "modules": {},
        }
        with patch("scitex_dev.docs.discover_packages", return_value={"pkg": "mod"}):
            with patch("scitex_dev.docs.get_docs", return_value=manifest):
                # Direct call to avoid recursion — test _get_one separately
                pass

        # Test with mock at the right level
        with patch("scitex_dev.docs.discover_packages", return_value={"pkg": "mod"}):
            with patch("scitex_dev.docs._get_one", return_value=manifest):
                result = search_docs(query="api")

        assert len(result) >= 1
        assert result[0]["name"] == "api"

    def test_search_max_results(self):
        manifest = {
            "pages": [
                {"name": f"page{i}", "title": f"Page {i} test"} for i in range(20)
            ],
            "modules": {},
        }
        with patch("scitex_dev.docs.discover_packages", return_value={"pkg": "mod"}):
            with patch("scitex_dev.docs._get_one", return_value=manifest):
                result = search_docs(query="test", max_results=5)

        assert len(result) <= 5


class TestBuildDocs:
    def test_build_unknown_package(self):
        with patch("scitex_dev.docs.discover_packages", return_value={}):
            with pytest.raises(LookupError, match="not found"):
                build_docs(package="nonexistent")
