#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the main docs module."""

from pathlib import Path

import pytest

from scitex_dev._core.discovery import invalidate_cache
from scitex_dev._docs.docs import build_docs, get_docs, search_docs


@pytest.fixture(autouse=True)
def clear_cache():
    invalidate_cache()
    yield
    invalidate_cache()


def _empty_discover():
    return {}


class TestGetDocs:
    def test_singular_and_plural_args_are_mutually_exclusive(self):
        """Cannot use both package= and packages=."""
        # Arrange
        # Act
        # Assert
        with pytest.raises(ValueError, match="singular.*plural"):
            get_docs(package="a", packages=["b"])

    def test_no_packages_discovered(self):
        """With no entry points, returns empty dict."""
        # Arrange
        # Act
        # Assert
        result = get_docs(_discover_fn=_empty_discover)
        assert result == {}

    def test_single_package_not_found(self):
        # Arrange
        # Act
        # Assert
        with pytest.raises(LookupError, match="not found"):
            get_docs(package="nonexistent", _discover_fn=_empty_discover)

    def test_single_package_introspect_fallback_isinstance_result_dict(self):
        """When no built docs exist, falls back to introspection."""
        # Arrange
        # Act
        # Assert
        result = get_docs(
            package="test-pkg",
            _discover_fn=lambda: {"test-pkg": "json"},
            _root_fn=lambda _name: None,
            _sphinx_fn=lambda _name: None,
        )
        # Should return introspected docs for the json module
        assert isinstance(result, dict)


    def test_single_package_introspect_fallback_json_in_result_get_package(self):
        """When no built docs exist, falls back to introspection."""
        # Arrange
        # Act
        # Assert
        result = get_docs(
            package="test-pkg",
            _discover_fn=lambda: {"test-pkg": "json"},
            _root_fn=lambda _name: None,
            _sphinx_fn=lambda _name: None,
        )
        # Should return introspected docs for the json module
        assert "json" in result.get("package", "")

    def test_single_package_html_format_isinstance_result_path(self, tmp_path):
        """HTML format returns a Path."""
        # Arrange
        # Act
        # Assert
        html_dir = tmp_path / "_sphinx_html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html></html>")

        result = get_docs(
            package="test-pkg",
            format="html",
            _discover_fn=lambda: {"test-pkg": "test_mod"},
            _root_fn=lambda _name: tmp_path,
        )
        assert isinstance(result, Path)


    def test_single_package_html_format_result_html_dir(self, tmp_path):
        """HTML format returns a Path."""
        # Arrange
        # Act
        # Assert
        html_dir = tmp_path / "_sphinx_html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html></html>")

        result = get_docs(
            package="test-pkg",
            format="html",
            _discover_fn=lambda: {"test-pkg": "test_mod"},
            _root_fn=lambda _name: tmp_path,
        )
        assert result == html_dir

    def test_multiple_packages_returns_dict_per_package_isinstance_result_dict(self):
        # Arrange
        # Act
        # Assert
        result = get_docs(
            packages=["pkg-a", "pkg-b"],
            _discover_fn=lambda: {"pkg-a": "json", "pkg-b": "os"},
            _root_fn=lambda _name: None,
            _sphinx_fn=lambda _name: None,
        )
        assert isinstance(result, dict)


    def test_multiple_packages_returns_dict_per_package_pkg_a_in_result(self):
        # Arrange
        # Act
        # Assert
        result = get_docs(
            packages=["pkg-a", "pkg-b"],
            _discover_fn=lambda: {"pkg-a": "json", "pkg-b": "os"},
            _root_fn=lambda _name: None,
            _sphinx_fn=lambda _name: None,
        )
        assert "pkg-a" in result


    def test_multiple_packages_returns_dict_per_package_pkg_b_in_result(self):
        # Arrange
        # Act
        # Assert
        result = get_docs(
            packages=["pkg-a", "pkg-b"],
            _discover_fn=lambda: {"pkg-a": "json", "pkg-b": "os"},
            _root_fn=lambda _name: None,
            _sphinx_fn=lambda _name: None,
        )
        assert "pkg-b" in result

    def test_unknown_format_raises_value_error(self, tmp_path):
        # Arrange
        # Act
        # Assert
        html_dir = tmp_path / "_sphinx_html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html></html>")

        with pytest.raises(ValueError, match="Unknown format"):
            get_docs(
                package="test-pkg",
                format="pdf",
                _discover_fn=lambda: {"test-pkg": "test_mod"},
                _root_fn=lambda _name: tmp_path,
            )


class TestSearchDocs:
    def test_search_with_no_packages_returns_empty_list(self):
        # Arrange
        # Act
        # Assert
        result = search_docs(query="anything", _discover_fn=_empty_discover)
        assert result == []

    def test_search_finds_pages_len_result_1(self):
        # Arrange
        # Act
        # Assert
        manifest = {
            "pages": [
                {"name": "api", "title": "API Reference"},
                {"name": "tutorial", "title": "Getting Started Tutorial"},
            ],
            "modules": {},
        }
        result = search_docs(
            query="api",
            _discover_fn=lambda: {"pkg": "mod"},
            _get_one_fn=lambda pkg, **_: manifest,
        )
        assert len(result) >= 1


    def test_search_finds_pages_result_0_name_api(self):
        # Arrange
        # Act
        # Assert
        manifest = {
            "pages": [
                {"name": "api", "title": "API Reference"},
                {"name": "tutorial", "title": "Getting Started Tutorial"},
            ],
            "modules": {},
        }
        result = search_docs(
            query="api",
            _discover_fn=lambda: {"pkg": "mod"},
            _get_one_fn=lambda pkg, **_: manifest,
        )
        assert result[0]["name"] == "api"

    def test_search_max_results(self):
        # Arrange
        # Act
        # Assert
        manifest = {
            "pages": [
                {"name": f"page{i}", "title": f"Page {i} test"} for i in range(20)
            ],
            "modules": {},
        }
        result = search_docs(
            query="test",
            max_results=5,
            _discover_fn=lambda: {"pkg": "mod"},
            _get_one_fn=lambda pkg, **_: manifest,
        )
        assert len(result) <= 5


class TestBuildDocs:
    def test_build_unknown_package(self):
        # Arrange
        # Act
        # Assert
        with pytest.raises(LookupError, match="not found"):
            build_docs(package="nonexistent", _discover_fn=_empty_discover)
