#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the main docs module."""

import json
from pathlib import Path

import pytest

from scitex_dev._core.discovery import invalidate_cache
from scitex_dev._docs.docs import _resolve_from_built, build_docs, get_docs, search_docs


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


def _prepare_page_fixture(tmp_path, format, location, present):
    package = tmp_path / "package"
    source = tmp_path / "docs"
    html = package / "_sphinx_html" if location == "bundle" else source / "_build/html"
    if location != "absent":
        html.mkdir(parents=True)
        (html / "index.html").write_text("Unrelated index")
    if present:
        target = html if format != "json" or location == "bundle" else source / "_build/json"
        target.mkdir(parents=True, exist_ok=True)
        (target / ("owned.fjson" if format == "json" else "owned.html")).write_text(
            json.dumps({"body": "Requested body"}) if format == "json" else "Requested body"
        )
    return package, source


@pytest.mark.parametrize("format", [None, "html", "json"])
@pytest.mark.parametrize("location,present", [
    ("bundle", True), ("build", True), ("bundle", False),
    ("build", False), ("absent", False),
])
def test_named_page_preserves_scope_across_resolution_chain(tmp_path, format, location, present):
    # Arrange
    package, source = _prepare_page_fixture(tmp_path, format, location, present)
    expected = ("page", "Requested body") if present else ("missing", True)
    # Act
    try:
        result = get_docs(
            package="owned-docs", page="owned", format=format,
            _discover_fn=lambda: {"owned-docs": "json"},
            _root_fn=lambda name: package,
            _sphinx_fn=lambda name: source,
        )
        actual = ("page", result.get("body") if isinstance(result, dict) else result.read_text())
    except FileNotFoundError as error:
        actual = ("missing", "owned" in str(error) and "owned-docs" in str(error))
    # Assert
    assert actual == expected


def test_multiple_package_page_request_propagates_missing_page(tmp_path):
    # Arrange
    # Act
    # Assert
    with pytest.raises(FileNotFoundError, match="owned.*owned-docs"):
        get_docs(
            packages=["owned-docs"], page="owned", format="json",
            _discover_fn=lambda: {"owned-docs": "json"},
            _root_fn=lambda name: tmp_path,
            _sphinx_fn=lambda name: None,
        )


@pytest.mark.parametrize("format,name", [
    (None, "owned.html"), (None, "owned"), ("html", "owned.html"),
    ("html", "owned"), ("json", "owned.fjson"), ("json", "owned.json"),
])
def test_directory_cannot_satisfy_named_page(tmp_path, format, name):
    # Arrange
    (tmp_path / "_sphinx_html" / name).mkdir(parents=True)
    # Act
    # Assert
    with pytest.raises(FileNotFoundError, match="owned.*owned-docs"):
        get_docs(
            package="owned-docs", page="owned", format=format,
            _discover_fn=lambda: {"owned-docs": "json"},
            _root_fn=lambda name: tmp_path, _sphinx_fn=lambda name: None,
        )


@pytest.mark.parametrize("format,primary,fallback", [
    ("html", "owned.html", "owned"), ("json", "owned.fjson", "owned.json"),
])
def test_directory_does_not_hide_regular_fallback_page(tmp_path, format, primary, fallback):
    # Arrange
    html = tmp_path / "_sphinx_html"
    (html / primary).mkdir(parents=True)
    (html / fallback).write_text(json.dumps({"body": "Real page body"}))
    # Act
    result = get_docs(
        package="owned-docs", page="owned", format=format,
        _discover_fn=lambda: {"owned-docs": "json"},
        _root_fn=lambda name: tmp_path, _sphinx_fn=lambda name: None,
    )
    body = result.get("body") if isinstance(result, dict) else json.loads(result.read_text())["body"]
    # Assert
    assert body == "Real page body"


@pytest.fixture(params=["bundle", "json-only-build"])
def json_provider(tmp_path, request):
    """Use the same page assets in bundled and JSON-only Sphinx layouts."""
    package = tmp_path / "package"
    source = tmp_path / "docs"
    target = (
        package / "_sphinx_html"
        if request.param == "bundle"
        else source / "_build" / "json"
    )
    target.mkdir(parents=True)
    (target / "guide").mkdir()
    body = {"body": "<h1>Setup</h1>", "title": "Setup"}
    for name in ["index.fjson", "index.json", "guide/setup.fjson"]:
        (target / name).write_text(json.dumps(body))
    for name in ["manifest.json", "globalcontext.json", "searchindex.json"]:
        (target / name).write_text(json.dumps({"metadata": "not a page"}))
    (target / "not-a-page.fjson").mkdir()
    (target / "not-a-page.json").mkdir()
    return package, source, target, body


def _read_provider(package, source, **kwargs):
    """Exercise public resolution without installed provider dependencies."""
    return get_docs(
        package="owned-docs",
        _discover_fn=lambda: {"owned-docs": "json"},
        _root_fn=lambda _module: package,
        _sphinx_fn=lambda _module: source,
        **kwargs,
    )


def test_json_page_index_lists_nested_pages_once_without_controls(json_provider):
    # Arrange
    package, source, _, _ = json_provider
    # Act
    result = _read_provider(package, source, format="json")
    # Assert
    assert result == {"pages": ["guide/setup", "index"]}


def test_listed_nested_json_page_can_be_read(json_provider):
    # Arrange
    package, source, _, body = json_provider
    # Act
    result = _read_provider(package, source, format="json", page="guide/setup")
    # Assert
    assert result == body


def test_nested_json_page_with_control_basename_is_not_root_metadata(json_provider):
    # Arrange
    package, source, target, body = json_provider
    (target / "guide/manifest.json").write_text(json.dumps(body))
    # Act
    result = _read_provider(package, source, format="json")
    # Assert
    assert result == {"pages": ["guide/manifest", "guide/setup", "index"]}


def test_json_index_falls_back_to_nested_regular_html_pages(tmp_path):
    # Arrange
    (tmp_path / "guide").mkdir()
    (tmp_path / "guide/setup.html").write_text("<h1>Setup</h1>")
    (tmp_path / "index.html").write_text("<h1>Home</h1>")
    (tmp_path / "directory.html").mkdir()
    (tmp_path / "manifest.json").write_text("{}")
    # Act
    result = _resolve_from_built(tmp_path, format="json")
    # Assert
    assert result == {
        "pages": ["guide/setup", "index"],
        "note": "JSON not built, listing HTML pages",
    }


def test_metadata_and_directories_alone_are_not_json_pages(tmp_path):
    # Arrange
    (tmp_path / "manifest.json").write_text("{}")
    (tmp_path / "globalcontext.json").write_text("{}")
    (tmp_path / "searchindex.json").write_text("{}")
    (tmp_path / "directory.fjson").mkdir()
    # Act
    result = _resolve_from_built(tmp_path, format="json")
    # Assert
    assert result is None
