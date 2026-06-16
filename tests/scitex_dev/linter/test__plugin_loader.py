#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev.linter._plugin_loader + the plugin-pipeline smoke.

Per neurovista elevation 2026-06-14: the figrecipe figure-style checkers
(FM P006-P011) were silently dead in every project because two
silent-degradation spots in scitex-dev's linter swallowed both the
load-time (circular-import) and the visit-time exceptions. Lint passed
false-green for months.

This module is the operator's "green support pipe under each red edge"
for the enforcement layer: it asserts the entry-point plugin loader
returns the schema downstream code destructures, every registered checker
constructs + visits a trivial AST without raising, and the fail-loud path
in ``lint_source`` surfaces (or, under the opt-out env flag, silences) a
dropped checker.

Real fakes only (PA-306 / STX-NM): the plugin payload is injected via
``lint_source``'s ``plugins=`` seam and env via a snapshot/restore
fixture — no monkeypatch.
"""

from __future__ import annotations

import ast
import os

import pytest

from scitex_dev.linter import _plugin_loader
from scitex_dev.linter.checker import lint_source


# --------------------------------------------------------------------------- #
# Fixtures + real fakes                                                        #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_plugin_cache():
    """Reset the plugin-loader cache around each test.

    ``load_plugins()`` is process-lifetime cached in production; tests need
    a fresh load each time so injection / env tweaks bite.
    """
    _plugin_loader.reset()
    yield
    _plugin_loader.reset()


@pytest.fixture
def restore_environ():
    """Snapshot + restore ``os.environ`` around a test.

    Real env manipulation (no mocks) — replaces ``monkeypatch.setenv`` /
    ``delenv`` per PA-306.
    """
    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


@pytest.fixture
def _trivial_tree():
    """An empty AST node — the cheapest visitable input."""
    return ast.parse("", filename="<test>")


class _BoomChecker:
    """Plugin-checker fake that always raises on visit (drives fail-loud).

    A real class, not a mock: ``lint_source`` constructs and visits it
    exactly as it would a registered plugin checker.
    """

    category = "stx-test"

    def __init__(self, lines, config):
        self.issues = []

    def visit(self, _tree):
        raise RuntimeError("synthetic-failure-for-pillar0-test")


def _payload_with(checker_cls):
    """A minimal ``load_plugins()``-shaped payload carrying one checker."""
    return {
        "rules": {},
        "call_rules": {},
        "axes_hints": {},
        "checkers": [checker_cls],
    }


# --------------------------------------------------------------------------- #
# load_plugins() smoke                                                         #
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
# Per-checker smoke                                                            #
# --------------------------------------------------------------------------- #


def test_every_registered_checker_constructs_without_raising(_trivial_tree):
    # Arrange — an empty venv (no plugins) makes this vacuously true; a real
    # checker that raises on construct/visit is what we want to catch.
    checkers = _plugin_loader.load_plugins()["checkers"]
    # Act — construct + visit each; collect any failures.
    failures: list[str] = []
    for cls in checkers:
        name = getattr(cls, "__name__", repr(cls))
        try:
            instance = cls([], None)
            instance.visit(_trivial_tree)
        except Exception as exc:  # noqa: BLE001 — we want the type+msg
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
    # Assert — a raise here means the checker would be silently dropped.
    assert failures == []


# --------------------------------------------------------------------------- #
# fail-loud path — lint_source plugins= seam (real fake, no monkeypatch)       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def broken_checker_stderr(capsys, restore_environ):
    """Run ``lint_source`` with an injected always-raising checker and the
    opt-out env unset; return ``(issues, stderr)``.

    The broken checker is supplied through the real ``plugins=`` seam — no
    loader patching.
    """
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    issues = lint_source(
        "x = 1\n", filepath="<test>", plugins=_payload_with(_BoomChecker)
    )
    captured = capsys.readouterr()
    return issues, captured.err


def test_lint_source_returns_list_despite_broken_checker(broken_checker_stderr):
    # Arrange
    issues, _err = broken_checker_stderr
    # Act
    # Assert — lint_source returns normally; other checkers' issues still flow.
    assert isinstance(issues, list)


def test_lint_source_warning_names_the_dropped_checker(broken_checker_stderr):
    # Arrange
    _issues, err = broken_checker_stderr
    # Act
    # Assert
    assert "_BoomChecker" in err


def test_lint_source_warning_includes_the_exception_message(broken_checker_stderr):
    # Arrange
    _issues, err = broken_checker_stderr
    # Act
    # Assert
    assert "synthetic-failure-for-pillar0-test" in err


def test_lint_source_silenced_by_env_flag(capsys, restore_environ):
    # Arrange — opt-out env set; same broken checker injected.
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    # Act
    lint_source("x = 1\n", filepath="<test>", plugins=_payload_with(_BoomChecker))
    captured = capsys.readouterr()
    # Assert — no stderr WARNING surfaces (operator opt-out respected).
    assert "synthetic-failure-for-pillar0-test" not in captured.err
