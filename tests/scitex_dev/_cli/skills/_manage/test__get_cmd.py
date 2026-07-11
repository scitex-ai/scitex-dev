"""Tests for `scitex-dev skills get` (`_get_cmd.py`).

No mocks: drives the REAL Click command tree via `click.testing.CliRunner`
against the real installed skills registry (scitex-dev ships its own
`_skills/` tree, so this is stable, non-flaky coverage).
"""

from __future__ import annotations

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli import main as cli


def test_skills_get_help_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(cli, ["skills", "get", "--help"])
    # Assert
    assert result.exit_code == 0


def test_skills_get_unknown_skill_exits_nonzero():
    # Arrange -- a skill name that certainly doesn't exist.
    runner = CliRunner()
    # Act
    result = runner.invoke(
        cli, ["skills", "get", "scitex-dev", "definitely-not-a-real-skill-xyz"]
    )
    # Assert
    assert result.exit_code != 0


def _first_real_skill_name(runner) -> str:
    """Resolve a real skill name for scitex-dev via `skills list --json`."""
    import json

    listing = runner.invoke(
        cli, ["skills", "list", "--package", "scitex-dev", "--json"]
    )
    payload = json.loads(listing.output)
    names = [s["name"] for s in payload.get("scitex-dev", [])]
    if not names:
        pytest.skip("scitex-dev ships no skills in this environment")
    return names[0]


def test_skills_get_drift_warning_does_not_crash():
    # Arrange -- regression guard: the original code called
    # `drift_warning(package)` without importing it, a latent NameError
    # that only fired on a successful lookup. Resolves a real skill name
    # first so the success path (where the bug lived) actually runs.
    runner = CliRunner()
    name = _first_real_skill_name(runner)
    # Act
    result = runner.invoke(cli, ["skills", "get", "scitex-dev", name])
    # Assert -- must NOT crash with NameError on the drift-warning path.
    assert result.exception is None
