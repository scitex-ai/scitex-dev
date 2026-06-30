#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev.linter._cmd_check — research-mode HARD ERROR on a
DECLARED-but-missing leaf plugin (kill the silent-skip false-green).

Live incident (NeuroVista 2026-06-30): a research venv was missing the
scitex-io plugin, so all IO/PA compliance rules SILENTLY did not fire and
``scitex-dev linter check-files`` reported "All files clean" — a false-green
that only broke once the plugin was installed. In ``project-type: research``
a DECLARED-but-unloadable plugin (or the canonical scitex-io-missing case)
must instead be a HARD ERROR (exit 2) so the post-edit hook (run_lint.sh,
exit 2) blocks. In NON-research dev venvs a missing leaf plugin is legitimate
and stays a warning. ``SCITEX_DEV_LINTER_QUIET=1`` is the documented escape
hatch (suppressed, NOT hard-failed).

The four cases the change must satisfy:
  (a) research + declared-but-unimportable plugin → HARD error (exit 2).
  (b) NON-research + same → NO hard error (exit stays 0/clean).
  (c) SCITEX_DEV_LINTER_QUIET=1 in research + broken plugin → suppressed.
  (d) all plugins load fine in research → no error.

Real fakes only (PA-306): the broken plugin is driven through the
``load_plugins(entry_points_iter=...)`` seam with a real fake entry point
whose ``.load()`` raises ``ModuleNotFoundError`` — no monkeypatch of
importlib.metadata, no mocks. Research-mode is a real tmp project carrying a
real ``.scitex/dev/config.yaml`` declaring ``project-type: research``.
"""

from __future__ import annotations

import os

import pytest

from scitex_dev.linter import _cmd_check, _health, _plugin_loader


# --------------------------------------------------------------------------- #
# Fixtures + real fakes                                                        #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset plugin-loader cache + health module-state around each test."""
    _plugin_loader.reset()
    _health.reset()
    yield
    _plugin_loader.reset()
    _health.reset()


@pytest.fixture
def restore_environ():
    """Snapshot + restore ``os.environ`` (no monkeypatch, per PA-306)."""
    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


class _StaleScitexEP:
    """Real fake of the dangling scitex-io entry point NeuroVista hit.

    ``.load()`` raises the exact ``ModuleNotFoundError`` a DECLARED-but-
    uninstalled/stale plugin produces — the entry point is present in
    installed metadata but the module is gone, so the rules never register.
    """

    name = "scitex_io"

    def load(self):
        raise ModuleNotFoundError(
            "No module named 'scitex_io._linter_plugin'",
            name="scitex_io._linter_plugin",
        )


def _one_broken_ep():
    return [_StaleScitexEP()]


def _record_broken_plugin_load():
    """Drive the loader's load-failure branch via the real injection seam.

    Calling ``load_plugins`` with a fake entry point whose ``.load()`` raises
    records the failure into ``_health._load_failures`` (the same path
    production takes), WITHOUT mocks. Returns nothing — the side effect is
    the recorded failure that ``research_blocking_conditions`` reads.
    """
    _plugin_loader.load_plugins(entry_points_iter=_one_broken_ep)


def _research_project(tmp_path, body):
    """Create a research-typed project dir with one Python ``body`` file.

    Writes a real ``.scitex/dev/config.yaml`` (``project-type: research``) so
    ``detect_scitex_dev_project_types`` reports research, mirroring how the
    linter resolves project-type in production. Returns the .py file path.
    """
    cfg = tmp_path / ".scitex" / "dev"
    cfg.mkdir(parents=True)
    (cfg / "config.yaml").write_text("project-type: research\n", encoding="utf-8")
    pyfile = tmp_path / "script.py"
    pyfile.write_text(body, encoding="utf-8")
    return str(pyfile)


def _plain_project(tmp_path, body):
    """Create a NON-research project dir (no .scitex marker) with one .py file."""
    pyfile = tmp_path / "script.py"
    pyfile.write_text(body, encoding="utf-8")
    return str(pyfile)


# A trivially-clean script: no source-content findings, so the ONLY thing
# that can drive exit 2 is the synthetic plugin-health error.
_CLEAN_BODY = "x = 1\n"


# --------------------------------------------------------------------------- #
# (a) research + declared-but-unimportable plugin → HARD error (exit 2)        #
# --------------------------------------------------------------------------- #


def test_research_broken_plugin_makes_do_check_exit_2(tmp_path, restore_environ):
    # Arrange — research project + a recorded declared-but-broken plugin.
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    restore_environ.pop("SCITEX_DEV_NO_AUDIT_DISCLAIMER", None)
    pyfile = _research_project(tmp_path, _CLEAN_BODY)
    _record_broken_plugin_load()
    # Act — the hook's BLOCKING pass uses --severity error.
    rc = _cmd_check._do_check(
        pyfile, as_json=False, no_color=True, severity="error", category=None
    )
    # Assert — silent-skip is now a HARD failure the hook treats as error.
    assert rc == 2


def test_research_broken_plugin_emits_error_finding_in_json(tmp_path, restore_environ):
    # Arrange
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    pyfile = _research_project(tmp_path, _CLEAN_BODY)
    _record_broken_plugin_load()
    # Act
    rc = _cmd_check._do_check(
        pyfile, as_json=True, no_color=True, severity="error", category=None
    )
    # Assert — JSON path sets exit 2 on the synthetic error finding too.
    assert rc == 2


def _research_broken_plugin_output(tmp_path, restore_environ, capsys):
    """Run ``_do_check`` (research + broken plugin) and return stdout."""
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    pyfile = _research_project(tmp_path, _CLEAN_BODY)
    _record_broken_plugin_load()
    _cmd_check._do_check(
        pyfile, as_json=False, no_color=True, severity="error", category=None
    )
    return capsys.readouterr().out


def test_research_broken_plugin_finding_names_the_plugin(tmp_path, restore_environ, capsys):
    # Arrange
    out = _research_broken_plugin_output(tmp_path, restore_environ, capsys)
    # Act
    # Assert — the finding names the broken plugin so the operator can act.
    assert "scitex_io" in out


def test_research_broken_plugin_finding_carries_fix_hint(tmp_path, restore_environ, capsys):
    # Arrange
    out = _research_broken_plugin_output(tmp_path, restore_environ, capsys)
    # Act
    # Assert — the actionable remediation rides along (reused _remediation_hint).
    assert "pip install" in out


# --------------------------------------------------------------------------- #
# (b) NON-research + same → only L1 warning, NO hard error (exit 0)            #
# --------------------------------------------------------------------------- #


def test_non_research_broken_plugin_does_not_hard_fail(tmp_path, restore_environ):
    # Arrange — same broken plugin, but a NON-research project.
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    pyfile = _plain_project(tmp_path, _CLEAN_BODY)
    _record_broken_plugin_load()
    # Act
    rc = _cmd_check._do_check(
        pyfile, as_json=False, no_color=True, severity="error", category=None
    )
    # Assert — non-research dev venvs legitimately lack leaf plugins → exit 0.
    assert rc == 0


def test_non_research_broken_plugin_research_conditions_empty(restore_environ):
    # Arrange — the pure decision function is the single source of truth.
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    _record_broken_plugin_load()
    # Act
    conditions = _health.research_blocking_conditions(research=False)
    # Assert
    assert conditions == []


# --------------------------------------------------------------------------- #
# (c) QUIET=1 in research + broken plugin → suppressed (no hard error)         #
# --------------------------------------------------------------------------- #


def test_quiet_env_suppresses_hard_fail_in_research(tmp_path, restore_environ):
    # Arrange — research + broken plugin, but the documented opt-out is set.
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    pyfile = _research_project(tmp_path, _CLEAN_BODY)
    _record_broken_plugin_load()
    # Act
    rc = _cmd_check._do_check(
        pyfile, as_json=False, no_color=True, severity="error", category=None
    )
    # Assert — escape hatch wins: suppressed, NOT hard-failed.
    assert rc == 0


def test_quiet_env_yields_no_research_conditions(restore_environ):
    # Arrange
    restore_environ["SCITEX_DEV_LINTER_QUIET"] = "1"
    _record_broken_plugin_load()
    # Act
    conditions = _health.research_blocking_conditions(research=True)
    # Assert
    assert conditions == []


def test_legacy_quiet_alias_also_suppresses(tmp_path, restore_environ):
    # Arrange — the legacy SCITEX_DEV_NO_AUDIT_DISCLAIMER switch is honoured too.
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    restore_environ["SCITEX_DEV_NO_AUDIT_DISCLAIMER"] = "1"
    pyfile = _research_project(tmp_path, _CLEAN_BODY)
    _record_broken_plugin_load()
    # Act
    rc = _cmd_check._do_check(
        pyfile, as_json=False, no_color=True, severity="error", category=None
    )
    # Assert
    assert rc == 0


# --------------------------------------------------------------------------- #
# (d) all plugins load fine in research → no error                            #
# --------------------------------------------------------------------------- #


def test_research_no_broken_plugin_no_hard_fail(tmp_path, restore_environ):
    # Arrange — research project, NO recorded load failure. (The io-missing
    # L1 condition does not fire here because _health._loaded stays False
    # without a real load tally — we did not record an empty plugin load.)
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    pyfile = _research_project(tmp_path, _CLEAN_BODY)
    # Act — no _record_broken_plugin_load(); clean source body.
    rc = _cmd_check._do_check(
        pyfile, as_json=False, no_color=True, severity="error", category=None
    )
    # Assert — a healthy research env lints clean (exit 0).
    assert rc == 0


def test_research_no_failure_conditions_empty(restore_environ):
    # Arrange — no load failure recorded, plugins healthy.
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    # Act
    conditions = _health.research_blocking_conditions(research=True)
    # Assert — declared-but-broken set is empty AND io-missing predicate is
    # not satisfied (no load tally), so no hard-fail condition.
    assert conditions == []


# --------------------------------------------------------------------------- #
# scitex-io-missing canonical false-green (the NeuroVista live hit)            #
# --------------------------------------------------------------------------- #


@pytest.fixture
def io_missing_research_conditions(restore_environ):
    """Yield the research conditions for the EXACT NeuroVista state.

    A plugin load completed but registered ZERO IO/PA rules and scitex-io is
    not importable. ``record_plugin_load([])`` drives the real path (no
    mocks); the io-missing predicate only fires when scitex_io is genuinely
    absent, so we skip when the env happens to ship it.
    """
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    _health.record_plugin_load([])  # zero IO/PA rules registered
    if _health._scitex_io_installed():
        pytest.skip("scitex_io importable in this env — io-missing case N/A")
    return _health.research_blocking_conditions(research=True)


def test_io_missing_is_research_hard_fail_condition(io_missing_research_conditions):
    # Arrange
    ids = {c["id"] for c in io_missing_research_conditions}
    # Act
    # Assert — the canonical silent-skip is surfaced as a research hard-fail.
    assert "STX-PLUGIN-IO-MISSING" in ids


def test_io_missing_not_hard_fail_in_non_research(restore_environ):
    # Arrange
    restore_environ.pop("SCITEX_DEV_LINTER_QUIET", None)
    _health.record_plugin_load([])
    # Act
    conditions = _health.research_blocking_conditions(research=False)
    # Assert — non-research stays warn-only.
    assert conditions == []


# EOF
