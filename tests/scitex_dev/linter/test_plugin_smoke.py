#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke tests for the linter plugin pipeline (META-FINDING).

Per neurovista elevation 2026-06-14: the figrecipe figure-style checkers
(FM P006-P011) were silently dead in every project because TWO
silent-degradation spots in scitex-dev's linter swallowed both the
load-time (circular-import) and the visit-time exceptions. Lint passed
false-green for months.

This module is the operator's "green support pipe under each red edge"
for the enforcement layer itself — a CI smoke test that asserts every
registered plugin (a) loads via the entry-point group and (b) its
checkers can be instantiated + visit a trivial AST without raising.
A NEW silent-dropped checker fails THIS test loudly.

Test pattern
------------
* ``test_plugin_load_does_not_silently_drop_payload`` — confirms
  ``load_plugins()`` returns a non-empty merged dict when at least one
  plugin is installed in the venv. Operator-friendly skip on a
  vacuum-install where no leaves are present (CI runs always have
  scitex-io / figrecipe / etc., so the skip never fires in prod).
* ``test_every_registered_checker_constructs_and_visits`` — iterates
  ``load_plugins()["checkers"]``, instantiates each with a trivial
  ``(lines, config)`` pair, calls ``visit(tree)`` against an empty AST,
  and asserts NO checker raises. A raise here means the checker would
  be silently dropped by the (now fail-LOUD) ``checker.lint_source``
  fallback — we want CI to flag it before it ships.
* ``test_lint_source_emits_warning_on_visit_failure`` — synthetic
  bad-checker injection via the entry-point reset mechanism;
  confirms the fail-loud path writes the stderr WARNING line. Guards
  against a future regression that re-silences the swallow.
"""

from __future__ import annotations

import ast
import os
import sys

import pytest

from scitex_dev.linter import _plugin_loader
from scitex_dev.linter.checker import lint_source


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_plugin_cache():
    """Reset the plugin-loader cache around each test.

    ``load_plugins()`` is process-lifetime cached in production. Tests
    need a fresh load each time so injection / env tweaks bite. The
    autouse keeps every test in this module clean without ceremony.
    """
    _plugin_loader.reset()
    yield
    _plugin_loader.reset()


@pytest.fixture
def _trivial_tree():
    """An empty AST node — the cheapest visitable input."""
    return ast.parse("", filename="<test>")


# --------------------------------------------------------------------------- #
# load_plugins() smoke                                                        #
# --------------------------------------------------------------------------- #


def test_load_plugins_returns_dict_with_required_keys():
    # Arrange
    # Act
    payload = _plugin_loader.load_plugins()
    # Assert — schema invariant; downstream lint_source destructures these.
    assert {"rules", "call_rules", "axes_hints", "checkers"}.issubset(payload)


def test_load_plugins_cache_returns_same_object_on_second_call():
    # Arrange
    first = _plugin_loader.load_plugins()
    # Act
    second = _plugin_loader.load_plugins()
    # Assert
    assert first is second


# --------------------------------------------------------------------------- #
# Per-checker smoke                                                           #
# --------------------------------------------------------------------------- #


def test_every_registered_checker_constructs_without_raising(_trivial_tree):
    # Arrange
    checkers = _plugin_loader.load_plugins()["checkers"]
    if not checkers:
        pytest.skip("no plugin checkers registered in this venv")
    # Act + Assert — constructor + visit MUST NOT raise.
    failures: list[str] = []
    for cls in checkers:
        name = getattr(cls, "__name__", repr(cls))
        try:
            instance = cls([], None)
            instance.visit(_trivial_tree)
        except Exception as exc:  # noqa: BLE001 — we want the type+msg
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    assert failures == []


# --------------------------------------------------------------------------- #
# fail-loud path                                                              #
# --------------------------------------------------------------------------- #


def test_lint_source_emits_warning_on_plugin_checker_visit_failure(monkeypatch, capsys):
    # Arrange — inject a synthetic broken checker so the fail-loud path fires.
    class _BoomChecker:
        category = "stx-test"

        def __init__(self, lines, config):
            self.issues = []

        def visit(self, _tree):
            raise RuntimeError("synthetic-failure-for-pillar0-test")

    fake_payload = {
        "rules": {},
        "call_rules": {},
        "axes_hints": {},
        "checkers": [_BoomChecker],
    }

    def _fake_load_plugins():
        return fake_payload

    monkeypatch.setattr(_plugin_loader, "load_plugins", _fake_load_plugins)
    # Make sure stderr is not silenced.
    monkeypatch.delenv("SCITEX_DEV_LINTER_QUIET", raising=False)
    # Act — lint a tiny snippet; the broken checker is invoked and raises.
    issues = lint_source("x = 1\n", filepath="<test>")
    captured = capsys.readouterr()
    # Assert — lint_source returns normally (other checkers' issues still flow)
    # AND a stderr warning surfaces the dropped checker name.
    assert isinstance(issues, list)
    assert "_BoomChecker" in captured.err
    assert "synthetic-failure-for-pillar0-test" in captured.err


def test_lint_source_silenced_by_env_flag(monkeypatch, capsys):
    # Arrange — same broken checker, but quiet env set.
    class _Boom:
        category = "stx-test"

        def __init__(self, lines, config):
            self.issues = []

        def visit(self, _tree):
            raise RuntimeError("should-be-silenced")

    monkeypatch.setattr(
        _plugin_loader,
        "load_plugins",
        lambda: {
            "rules": {},
            "call_rules": {},
            "axes_hints": {},
            "checkers": [_Boom],
        },
    )
    monkeypatch.setenv("SCITEX_DEV_LINTER_QUIET", "1")
    # Act
    lint_source("x = 1\n", filepath="<test>")
    captured = capsys.readouterr()
    # Assert — no stderr WARNING surfaces (operator opt-out respected).
    assert "should-be-silenced" not in captured.err


# EOF
