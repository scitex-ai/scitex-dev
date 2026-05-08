"""Smoke tests for the ecosystem dashboard renderer."""

from __future__ import annotations


def test_module_imports():
    import importlib

    importlib.import_module("scitex_dev._cli.ecosystem._dashboard._render")
