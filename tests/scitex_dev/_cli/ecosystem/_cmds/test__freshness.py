"""CLI wiring for deterministic organization freshness GC."""

from __future__ import annotations

from datetime import datetime, timezone

import click
from click.testing import CliRunner
from scitex_dev._cli.ecosystem._cmds import _freshness
from scitex_dev._core.config import DevConfig, FreshnessConfig
from scitex_dev._ecosystem.freshness_gc import (
    CardsResult,
    FreshnessResult,
    GitHubCounts,
)


def _result(policy, now, dry_run):
    return FreshnessResult(
        organization=policy.organization,
        freshness_days=policy.freshness_days,
        now=now,
        cutoff=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        dry_run=dry_run,
        github=GitHubCounts(examined=5, candidates=2, closed=0),
        cards=CardsResult(available=False, invoked=False, required=False),
    )


def _cli(calls):
    @click.group()
    def root():
        pass

    def run_fn(**kwargs):
        calls.append(kwargs)
        return _result(kwargs["policy"], kwargs["now"], kwargs["dry_run"])

    _freshness.register(
        root,
        run_fn=run_fn,
        load_config_fn=lambda: DevConfig(
            freshness=FreshnessConfig(
                organization="scitex-ai", freshness_days=3, cards="auto"
            )
        ),
    )
    return root


def test_cli_injects_now_and_emits_json_counts():
    # Arrange
    calls = []
    cli = _cli(calls)
    # Act
    result = CliRunner().invoke(
        cli,
        [
            "apply-freshness-gc",
            "--now",
            "2026-09-17T12:00:00Z",
            "--dry-run",
            "--json",
            "--no-cards",
        ],
    )
    actual = (result.exit_code, '"candidates": 2' in result.output)
    # Assert
    assert actual == (0, True)


def test_cli_uses_default_three_day_policy():
    # Arrange
    calls = []
    cli = _cli(calls)
    # Act
    CliRunner().invoke(
        cli,
        [
            "apply-freshness-gc",
            "--now",
            "2026-09-17T12:00:00Z",
            "--dry-run",
            "--no-cards",
        ],
    )
    # Assert
    assert calls[0]["policy"].freshness_days == 3


def test_cli_cards_flag_requests_required_integration():
    # Arrange
    calls = []
    cli = _cli(calls)
    # Act
    CliRunner().invoke(
        cli,
        [
            "apply-freshness-gc",
            "--now",
            "2026-09-17T12:00:00Z",
            "--dry-run",
            "--cards",
        ],
    )
    # Assert
    assert calls[0]["cards_mode"] == "required"


def test_cli_apply_requires_yes_confirmation():
    # Arrange
    calls = []
    cli = _cli(calls)
    # Act
    result = CliRunner().invoke(
        cli,
        ["apply-freshness-gc", "--apply", "--no-cards"],
    )
    # Assert
    assert result.exit_code == 2
