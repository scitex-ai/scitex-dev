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


class _ConfigReadingChecker:
    """Plugin-checker fake mirroring figrecipe's StyleKwarg checker: it
    dereferences ``self.config.disable`` on visit.

    The scitex-io self-hosted-runner crash (routed via scitex-hpc): on the
    ``lint_source(config=None)`` path the plugin loop handed the raw ``None``
    to this constructor, so ``self.config.disable`` raised AttributeError and
    the checker was silently dropped. ``lint_source`` must pass the RESOLVED
    config (never None), exactly as the core SciTeXChecker receives.
    """

    category = "stx-test"

    def __init__(self, lines, config):
        self.config = config
        self.issues = []

    def visit(self, _tree):
        # The exact deref that crashed on a None config.
        if "STX-NEVER-DISABLED" in self.config.disable:  # pragma: no cover
            self.issues.append("unreachable")


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


def test_plugin_checker_receives_resolved_config_when_none(capsys, restore_environ):
    # Arrange — lint_source's documented config=None path. A plugin checker
    # that reads self.config.disable must get the RESOLVED config (loaded via
    # load_config), not a raw None — else it AttributeErrors and is dropped
    # (the scitex-io StyleKwarg crash on test__pdf*.py).
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    # Act
    lint_source(
        "x = 1\n",
        filepath="<test>",
        config=None,
        plugins=_payload_with(_ConfigReadingChecker),
    )
    err = capsys.readouterr().err
    # Assert — not dropped: no fail-loud WARNING names the config-reading checker.
    assert "_ConfigReadingChecker" not in err


# --------------------------------------------------------------------------- #
# LOAD-time fail-loud — entry_points_iter seam (real fake entry points)        #
#                                                                              #
# Ask 2 (neurovista 2026-06-14): a plugin advertised via the                   #
# `scitex_dev.linter.plugins` entry-point group but unimportable must FAIL     #
# LOUD + ACTIONABLE — not a swallowed/duplicated noisy line. The              #
# `scitex` symptom is a STALE wheel whose entry point points at a dropped      #
# `scitex._linter_plugin` module. We drive that branch with a real fake        #
# entry point (a real class whose `.load()` raises), through the               #
# `entry_points_iter` seam — no monkeypatch of importlib.metadata.             #
# --------------------------------------------------------------------------- #


class _StaleScitexEP:
    """Real fake of the dangling `scitex` entry point neurovista hit.

    Its ``.load()`` raises the exact ``ModuleNotFoundError`` an OLD scitex
    wheel produces — the entry point outlived the module it points at.
    """

    name = "scitex"

    def load(self):
        raise ModuleNotFoundError(
            "No module named 'scitex._linter_plugin'",
            name="scitex._linter_plugin",
        )


class _CircularImportEP:
    """Real fake of a plugin module that raises a circular ImportError."""

    name = "figrecipe"

    def load(self):
        raise ImportError("cannot import name 'X' (most likely a circular import)")


def _one_stale_ep():
    return [_StaleScitexEP()]


def _no_eps():
    return []


@pytest.fixture
def stale_plugin_stderr(capsys, restore_environ):
    """Load plugins with one stale entry point + opt-out unset; return stderr."""
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    restore_environ.pop("SCITEX_DEV_NO_AUDIT_DISCLAIMER", None)
    _plugin_loader.load_plugins(entry_points_iter=_one_stale_ep)
    return capsys.readouterr().err


def test_load_failure_warning_names_the_plugin(stale_plugin_stderr):
    # Arrange
    err = stale_plugin_stderr
    # Act
    # Assert
    assert "'scitex'" in err


def test_load_failure_warning_names_the_missing_module(stale_plugin_stderr):
    # Arrange
    err = stale_plugin_stderr
    # Act
    # Assert — the actual dangling module is named so the operator can act.
    assert "scitex._linter_plugin" in err


def test_load_failure_warning_is_actionable_with_reinstall_hint(stale_plugin_stderr):
    # Arrange
    err = stale_plugin_stderr
    # Act
    # Assert — a concrete next step, not just the bare exception.
    assert "pip install" in err


def test_load_failure_warning_diagnoses_stale_entry_point(stale_plugin_stderr):
    # Arrange
    err = stale_plugin_stderr
    # Act
    # Assert — distinguishes "stale wheel" from "broken module".
    assert "STALE" in err


def test_load_failure_warning_mentions_quiet_escape(stale_plugin_stderr):
    # Arrange
    err = stale_plugin_stderr
    # Act
    # Assert
    assert "SCITEX_DEV_LINTER_QUIET" in err


def test_load_failure_does_not_duplicate_the_bare_exception_line(stale_plugin_stderr):
    # Arrange — the old code emitted the same `failed to load plugin` text
    # TWICE (logger.warning + stderr.write). Exactly one copy must reach
    # stderr now; the logger breadcrumb is debug-level (not captured here).
    err = stale_plugin_stderr
    # Act
    occurrences = err.count("failed to load plugin")
    # Assert
    assert occurrences == 1


def test_load_failure_payload_is_still_well_formed():
    # Arrange — a failed plugin must not corrupt the merged payload shape.
    payload = _plugin_loader.load_plugins(entry_points_iter=_one_stale_ep)
    # Act
    # Assert
    assert {"rules", "call_rules", "axes_hints", "checkers"}.issubset(payload)


def test_load_failure_drops_only_the_broken_plugins_rules():
    # Arrange
    payload = _plugin_loader.load_plugins(entry_points_iter=_one_stale_ep)
    # Act
    # Assert — the broken plugin contributed nothing (no partial registration).
    assert payload["rules"] == {}


def test_no_declared_plugins_is_silent(capsys, restore_environ):
    # Arrange — an empty entry-point group is FINE (engine-only venv) and
    # must NOT emit the load-failure warning. This is the "no plugins
    # declared" case that must stay distinct from "declared-but-broken".
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    restore_environ.pop("SCITEX_DEV_NO_AUDIT_DISCLAIMER", None)
    # Act
    _plugin_loader.load_plugins(entry_points_iter=_no_eps)
    err = capsys.readouterr().err
    # Assert
    assert "failed to load plugin" not in err


def test_load_failure_silenced_by_quiet_env(capsys, restore_environ):
    # Arrange — opt-out env set; same stale entry point.
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    # Act
    _plugin_loader.load_plugins(entry_points_iter=_one_stale_ep)
    err = capsys.readouterr().err
    # Assert — operator opt-out silences the load-failure notice too.
    assert "failed to load plugin" not in err


def test_injected_entry_points_do_not_pollute_the_process_cache():
    # Arrange — the seam exists for tests; it must never write the
    # process-lifetime cache (production load stays authoritative).
    _plugin_loader.reset()
    # Act
    _plugin_loader.load_plugins(entry_points_iter=_one_stale_ep)
    # Assert
    assert _plugin_loader._cache is None


# --------------------------------------------------------------------------- #
# _remediation_hint — pure function, both failure shapes                       #
# --------------------------------------------------------------------------- #


def test_remediation_hint_for_missing_linter_plugin_module_says_stale():
    # Arrange
    exc = ModuleNotFoundError(
        "No module named 'scitex._linter_plugin'", name="scitex._linter_plugin"
    )
    # Act
    hint = _plugin_loader._remediation_hint("scitex", exc)
    # Assert
    assert "STALE" in hint


def test_remediation_hint_for_missing_module_names_the_distribution():
    # Arrange
    exc = ModuleNotFoundError(
        "No module named 'scitex._linter_plugin'", name="scitex._linter_plugin"
    )
    # Act
    hint = _plugin_loader._remediation_hint("scitex", exc)
    # Assert — the reinstall target is the distribution, not the submodule.
    assert "scitex" in hint


def test_remediation_hint_for_circular_import_names_circular():
    # Arrange
    exc = ImportError("cannot import name 'X' (most likely a circular import)")
    # Act
    hint = _plugin_loader._remediation_hint("figrecipe", exc)
    # Assert — the broken-module branch points at the circular import.
    assert "circular import" in hint


def test_circular_import_plugin_failure_is_actionable(capsys, restore_environ):
    # Arrange — a plugin whose module exists but raises on import.
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    restore_environ.pop("SCITEX_DEV_NO_AUDIT_DISCLAIMER", None)
    # Act
    _plugin_loader.load_plugins(entry_points_iter=lambda: [_CircularImportEP()])
    err = capsys.readouterr().err
    # Assert
    assert "circular import" in err
