"""Tests for scitex_dev.linter._health — Pillar-0 fail-loud notices.

Two silent-skip paths the 2026-06-12 ripple-wm dogfood pinned:

* **L1** — plugin discovery returns zero IO/PA category rules because
  scitex-io is missing → IO0xx rules cannot register → previously the
  linter said "All files clean" on a script with `pd.read_parquet`.
* **L2** — `requires="scitex"` gate fires on every IO/PA rule because
  the umbrella isn't import-detectable → rules drop silently on each
  file → same false-clean state.

These tests pin that both notices land on stderr exactly once per
process, gate cleanly on `SCITEX_DEV_LINTER_QUIET=1`, and that
`record_plugin_load` is a no-op when an IO plugin DID register.

Test isolation note: each test runs in its own subprocess so the
module-global emit-once flags (``_emitted_l1`` / ``_emitted_l2``) are
fresh. The first line of every script that probes a NEW emission sets
``SCITEX_DEV_LINTER_QUIET=1`` so the import-time pass through
``_register_sweep_cli`` → ``load_plugins`` → ``record_plugin_load([])``
chain (which would naturally fire L1 in this sparse venv) stays
silent — then the env var is dropped, ``_health.reset()`` clears the
state, and the explicit test call exercises the predicate the test
cares about. Without this, every test would see one import-time L1
emission inherited from a context the test isn't testing.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest


# ---------------------------------------------------------------------- #
# Helpers — keep production code self-contained, use a real subprocess   #
# so each test starts with a clean import / module-state slate. The     #
# stderr-emission contract is process-wide so in-process pytest can     #
# accidentally cross-pollinate state between tests.                     #
# ---------------------------------------------------------------------- #


# Boilerplate prepended to every test script: import scitex_dev with the
# QUIET env set so the import-time L1 emission (which always fires in
# this sparse agent venv) does not leak into the stderr the test asserts
# against. Then env-drop + reset so the explicit call below runs against
# fresh module state.
_QUIET_IMPORT_BOILERPLATE = """
    import os
    os.environ['SCITEX_DEV_LINTER_QUIET'] = '1'
    from scitex_dev.linter import _health
    from scitex_dev.linter._rules._base import Rule
    os.environ.pop('SCITEX_DEV_LINTER_QUIET', None)
    _health.reset()
"""


def _run(script: str, env_extra: dict | None = None, prepend_boilerplate: bool = True) -> subprocess.CompletedProcess:
    """Run a Python one-liner with the current interpreter; return result.

    When ``prepend_boilerplate`` is True (default), the QUIET-import +
    reset prelude runs first so the test's assertion sees only the
    emissions the test triggers — never the import-time L1 inherited
    from the sparse venv.
    """
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    body = textwrap.dedent(script)
    if prepend_boilerplate:
        body = textwrap.dedent(_QUIET_IMPORT_BOILERPLATE) + body
    return subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        env=env,
    )


# ---------------------------------------------------------------------- #
# L1 — plugin-discovery fail-loud                                        #
# ---------------------------------------------------------------------- #


class TestL1PluginDiscoveryFailLoud:
    """L1 fires when 0 IO/PA rules registered AND scitex-io is missing."""

    def test_emits_on_zero_io_plugins_when_scitex_io_absent(self):
        # Arrange — empty plugin payload (no scitex-io registered).
        # The QUIET-import boilerplate (see _QUIET_IMPORT_BOILERPLATE)
        # already imported _health under QUIET=1, dropped the env, and
        # called reset(). So this record_plugin_load is the first
        # post-reset emission opportunity.
        script = """
            _health.record_plugin_load([])
        """
        # Act
        result = _run(script)
        # Assert
        assert "no IO/PA category rules" in result.stderr, (
            f"L1 must fire on empty plugin set; stderr={result.stderr!r}"
        )

    def test_does_not_emit_when_quiet_env_set(self):
        # Arrange — leave QUIET=1 set throughout the script body (the
        # boilerplate drops it after import; we re-set it here).
        script = """
            os.environ['SCITEX_DEV_LINTER_QUIET'] = '1'
            _health.record_plugin_load([])
        """
        # Act
        result = _run(script)
        # Assert
        assert "no IO/PA category rules" not in result.stderr, (
            "L1 must respect SCITEX_DEV_LINTER_QUIET=1"
        )

    def test_does_not_emit_when_an_io_plugin_already_registered(self):
        # Arrange — synthetic plugin payload with a category="io" rule.
        script = """
            io_rule = Rule(
                id='STX-IO-FAKE',
                severity='warning',
                category='io',
                message='fake io rule',
                suggestion='fake suggestion',
            )
            _health.record_plugin_load([{'rules': [io_rule]}])
        """
        # Act
        result = _run(script)
        # Assert
        assert "no IO/PA category rules" not in result.stderr, (
            f"L1 must NOT fire when an io-category rule registers; "
            f"stderr={result.stderr!r}"
        )

    def test_emits_only_once_per_process_across_repeated_record_calls(self):
        # Arrange — call record_plugin_load three times with empty payloads.
        script = """
            _health.record_plugin_load([])
            _health.record_plugin_load([])
            _health.record_plugin_load([])
        """
        # Act
        result = _run(script)
        # Assert
        assert result.stderr.count("no IO/PA category rules") == 1, (
            f"L1 must emit exactly once per process; "
            f"got count={result.stderr.count('no IO/PA category rules')} "
            f"stderr={result.stderr!r}"
        )


# ---------------------------------------------------------------------- #
# L2 — requires-gate fail-loud                                           #
# ---------------------------------------------------------------------- #


class TestL2RequiresGateFailLoud:
    """L2 fires once when the requires= gate has dropped >=1 rule."""

    def test_emits_on_first_skip(self):
        # Arrange
        script = """
            _health.record_rule_skip('scitex')
        """
        # Act
        result = _run(script)
        # Assert
        assert "silently skipped via `requires=` gate" in result.stderr, (
            f"L2 must fire on first requires-gate skip; stderr={result.stderr!r}"
        )

    def test_does_not_emit_when_quiet_env_set(self):
        # Arrange
        script = """
            os.environ['SCITEX_DEV_LINTER_QUIET'] = '1'
            _health.record_rule_skip('scitex')
        """
        # Act
        result = _run(script)
        # Assert
        assert "silently skipped" not in result.stderr

    def test_emits_only_once_per_process_across_many_skips(self):
        # Arrange
        script = """
            for _ in range(50):
                _health.record_rule_skip('scitex')
        """
        # Act
        result = _run(script)
        # Assert
        assert result.stderr.count("silently skipped") == 1

    def test_aggregates_skips_in_snapshot_even_after_emission_fired(self):
        # Arrange — emit-once-then-keep-counting: the FIRST skip fires
        # the L2 message (so the agent feedback surface sees it quickly,
        # not at end of run). Subsequent skips keep incrementing the
        # snapshot counters so `linter doctor` / health_snapshot can
        # report the full picture later. This is the deliberate trade-
        # off — emit-on-first vs emit-at-end — and the snapshot is the
        # at-end view. Without this guard a regression that resets the
        # counter on emit would go un-caught.
        script = """
            import json
            os.environ['SCITEX_DEV_LINTER_QUIET'] = '1'  # avoid stderr noise
            _health.record_rule_skip('scitex')
            _health.record_rule_skip('scitex')
            _health.record_rule_skip('figrecipe')
            print(json.dumps(_health.health_snapshot()['skip_counts']))
        """
        # Act
        import json
        result = _run(script)
        skip_counts = json.loads(result.stdout.strip().splitlines()[-1])
        # Assert
        assert skip_counts == {"scitex": 2, "figrecipe": 1}, (
            f"snapshot must aggregate post-emission too; got {skip_counts}"
        )


# ---------------------------------------------------------------------- #
# health_snapshot                                                        #
# ---------------------------------------------------------------------- #


def test_health_snapshot_reports_recorded_state():
    # Arrange — record one skip with QUIET set so emission is suppressed
    # but the counter still increments; then read the snapshot.
    script = """
        import json
        os.environ['SCITEX_DEV_LINTER_QUIET'] = '1'
        _health.record_rule_skip('scitex')
        snap = _health.health_snapshot()
        print(json.dumps({
            'io_rule_count': snap['io_rule_count'],
            'skip_counts': snap['skip_counts'],
            'emitted_l2': snap['emitted_l2'],
        }))
    """
    # Act
    import json
    result = _run(script)
    snap = json.loads(result.stdout.strip().splitlines()[-1])
    # Assert
    assert snap == {
        "io_rule_count": 0,
        "skip_counts": {"scitex": 1},
        "emitted_l2": False,  # quiet mode → emission suppressed but count tracked
    }
