#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The skipped-category hint must name the interpreter, not "this venv".

Reported by figrecipe, measured 2026-08-09, and reproduced in this
container during the same session.

WHAT WENT WRONG. The hint said "the scitex-io plugin is not installed in
this venv. Fix: pip install scitex-io". figrecipe followed it exactly —
installed scitex-io into the venv they were working in, verified the import
from that interpreter — and the warning was IDENTICAL on the next run. The
linter does not run from the agent's working venv; it runs from the SAC venv
baked into the container image (`command -v scitex-dev` ->
/opt/venv-sac/bin/scitex-dev). Installing into the venv the reader is
standing in has no effect on it.

WHY THE PHRASE IS THE DEFECT. "this venv" means, to any reader, the venv
they are working in — which is precisely the one where the remedy does
nothing. So an agent that dutifully follows the tool's own advice sees no
change, concludes the notice is noise or unfixable, and carries on with 19
rules dark. That is the constitution's "everyone believes the check is
working" failure, reached by OBEYING the tool.

The cost was measured too: once figrecipe installed into the correct
interpreter, the linter immediately surfaced two real pre-existing warnings
that had been invisible all session.

NOTE ON METHOD. These tests drive the module's REAL recording API
(``record_rule_skip`` / ``reset``) rather than patching its internals, so
what is asserted is what production produces. The plugin-missing case is
exercised only when scitex_io is genuinely absent, because that record only
exists when it genuinely is — an environment where the plugin is installed
has nothing to assert about, and faking it would test the fake.
"""

from __future__ import annotations

import importlib.util
import sys

import pytest

from scitex_dev.linter import _health

_SCITEX_IO_PRESENT = importlib.util.find_spec("scitex_io") is not None


@pytest.fixture
def gated_skip_record() -> dict:
    """A real ``requires_gate`` record, produced by the real recording API."""
    _health.reset()
    _health.record_rule_skip("pandas")
    record = next(
        r for r in _health.skipped_categories() if r["kind"] == "requires_gate"
    )
    yield record
    _health.reset()


@pytest.fixture
def plugin_missing_record() -> dict:
    """The real ``plugin_missing`` record, via the real load path.

    ``record_plugin_load([])`` is exactly what the loader calls when no
    plugin contributed any io/path rules — the production condition this
    record reports on. Nothing is patched: the L1 notice then fires because
    ``scitex_io`` genuinely is not importable from this interpreter.

    Deliberately NOT `pytest.skip` when the record is missing. An earlier
    draft did that, and all three tests skipped silently while looking
    green — the inert-gate failure this very fix is about. If the record is
    absent the test FAILS and says why.
    """
    _health.reset()
    _health.record_plugin_load([])
    records = _health.skipped_categories()
    record = next(
        (r for r in records if r["kind"] == "plugin_missing"), None
    )
    assert record is not None, (
        "no plugin_missing record after record_plugin_load([]) with scitex_io "
        f"absent from {sys.executable}. Either the L1 condition changed or "
        f"scitex_io became importable; records were {records!r}"
    )
    yield record
    _health.reset()


def test_the_requires_gate_reason_names_the_running_interpreter(gated_skip_record):
    """The reason must identify WHICH interpreter cannot import it."""
    # Arrange
    expected = sys.executable

    # Act
    reason = gated_skip_record["reason"]

    # Assert
    assert expected in reason


def test_the_requires_gate_reason_does_not_say_this_venv(gated_skip_record):
    """The ambiguous phrase IS the defect, so assert it is gone."""
    # Arrange
    ambiguous = "this venv"

    # Act
    reason = gated_skip_record["reason"]

    # Assert
    assert ambiguous not in reason


def test_the_requires_gate_remedy_is_runnable_as_printed(gated_skip_record):
    """A bare `pip install` installs into the wrong place. Name the python."""
    # Arrange
    expected = f"{sys.executable} -m pip install pandas"

    # Act
    remedy = gated_skip_record["remedy"]

    # Assert
    assert remedy == expected


def test_the_requires_gate_record_exposes_the_interpreter_as_a_field(
    gated_skip_record,
):
    """Structured callers should not have to parse it out of prose."""
    # Arrange
    expected = sys.executable

    # Act
    actual = gated_skip_record["interpreter"]

    # Assert
    assert actual == expected


def test_the_rendered_line_carries_the_interpreter(gated_skip_record):
    """describe_skips() is what a human actually reads, so check it too."""
    # Arrange
    records = [gated_skip_record]

    # Act
    rendered = "\n".join(_health.describe_skips(records))

    # Assert
    assert sys.executable in rendered


def test_the_rendered_line_does_not_say_this_venv(gated_skip_record):
    """The rendered form is the one that misled a reader. Pin it."""
    # Arrange
    records = [gated_skip_record]

    # Act
    rendered = "\n".join(_health.describe_skips(records))

    # Assert
    assert "this venv" not in rendered


@pytest.mark.skipif(
    _SCITEX_IO_PRESENT, reason="scitex_io installed; no plugin_missing record exists"
)
def test_the_plugin_missing_reason_names_the_running_interpreter(
    plugin_missing_record,
):
    """The original report's exact case, on the real record."""
    # Arrange
    expected = sys.executable

    # Act
    reason = plugin_missing_record["reason"]

    # Assert
    assert expected in reason


@pytest.mark.skipif(
    _SCITEX_IO_PRESENT, reason="scitex_io installed; no plugin_missing record exists"
)
def test_the_plugin_missing_reason_does_not_say_this_venv(plugin_missing_record):
    """The phrase figrecipe followed into a no-op must be gone."""
    # Arrange
    ambiguous = "this venv"

    # Act
    reason = plugin_missing_record["reason"]

    # Assert
    assert ambiguous not in reason


@pytest.mark.skipif(
    _SCITEX_IO_PRESENT, reason="scitex_io installed; no plugin_missing record exists"
)
def test_the_plugin_missing_remedy_is_runnable_as_printed(plugin_missing_record):
    """This is the command figrecipe ran against the wrong interpreter."""
    # Arrange
    expected = f"{sys.executable} -m pip install scitex-io"

    # Act
    remedy = plugin_missing_record["remedy"]

    # Assert
    assert remedy == expected

# EOF
