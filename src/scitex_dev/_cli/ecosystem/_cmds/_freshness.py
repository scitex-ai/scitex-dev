"""``ecosystem apply-freshness-gc`` organization forgetting-policy command."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable

import click

from ...._core.config import load_config
from ...._ecosystem.freshness_gc import (
    FreshnessPolicy,
    parse_timestamp,
    run_freshness_gc,
)
from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register(
    ecosystem,
    *,
    run_fn: Callable = run_freshness_gc,
    load_config_fn: Callable = load_config,
):
    """Register the freshness command; dependencies are injectable for tests."""

    @ecosystem.command(
        "apply-freshness-gc",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Apply one freshness cutoff to organization work items.",
            description=(
                "Inventories every open issue and pull request in the configured "
                "GitHub organization and selects only items whose updatedAt is "
                "strictly older than the cutoff. Apply mode re-reads each candidate "
                "before closing it, so a concurrent update keeps it open. No "
                "comments or audit shadow files are created.",
                "The identical cutoff is forwarded to scitex-cards freshness-gc "
                "when available. --cards makes that integration required; "
                "--no-cards disables it; otherwise config uses auto detection.",
            ),
            examples=(
                Example(
                    "{prog} ecosystem apply-freshness-gc --dry-run --json",
                    "Preview the default 3-day policy.",
                ),
                Example(
                    "{prog} ecosystem apply-freshness-gc --apply --yes --cards",
                    "Apply and require Cards.",
                ),
                Example(
                    "{prog} ecosystem apply-freshness-gc --now 2026-09-17T12:00:00Z --dry-run",
                    "Run deterministically.",
                ),
            ),
            config_resolution=(
                "~/.scitex/dev/config.yaml: freshness.organization, "
                "freshness.freshness_days, freshness.cards; CLI options override.",
            ),
        ),
    )
    @click.option(
        "--days",
        type=click.IntRange(min=0),
        default=None,
        help="Override configured freshness_days (default: 3).",
    )
    @click.option(
        "--organization",
        default=None,
        help="Override the configured GitHub organization.",
    )
    @click.option(
        "--now",
        "now_text",
        default=None,
        help="UTC ISO-8601 clock injection for deterministic runs.",
    )
    @click.option(
        "--apply/--dry-run",
        default=False,
        help="Close/delete stale items; default is dry-run.",
    )
    @click.option(
        "--yes", is_flag=True, help="Confirm organization-wide mutation in apply mode."
    )
    @click.option(
        "--cards/--no-cards",
        default=None,
        help="Require or disable Cards; default is config/auto.",
    )
    @click.option(
        "--json", "as_json", is_flag=True, help="Emit machine-readable counts as JSON."
    )
    def freshness_gc(days, organization, now_text, apply, yes, cards, as_json):
        if apply and not yes:
            raise click.UsageError("--apply requires --yes.")
        cfg = load_config_fn()
        configured = cfg.freshness
        policy = FreshnessPolicy(
            organization=organization or configured.organization,
            freshness_days=configured.freshness_days if days is None else days,
        )
        try:
            now = parse_timestamp(now_text) if now_text else datetime.now(timezone.utc)
        except (TypeError, ValueError) as exc:
            raise click.BadParameter(str(exc), param_hint="--now") from exc

        if cards is True:
            cards_mode = "required"
        elif cards is False:
            cards_mode = "off"
        else:
            cards_mode = configured.cards

        try:
            result = run_fn(
                policy=policy,
                now=now,
                dry_run=not apply,
                cards_mode=cards_mode,
            )
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc

        payload = result.to_dict()
        if as_json:
            click.echo(json.dumps(payload, sort_keys=True))
            return

        counts = payload["github"]["counts"]
        mode = "dry-run" if payload["dry_run"] else "apply"
        click.echo(
            f"{payload['organization']}: cutoff={payload['cutoff']} mode={mode} "
            f"examined={counts['examined']} candidates={counts['candidates']} "
            f"closed={counts['closed']} freshened={counts['freshened']}"
        )
        card_counts = payload["cards"]["counts"]
        click.echo(
            "cards: "
            f"available={payload['cards']['available']} "
            f"invoked={payload['cards']['invoked']} "
            f"counts={json.dumps(card_counts, sort_keys=True)}"
        )

    return freshness_gc


__all__ = ["register"]
