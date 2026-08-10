#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex-dev cardsync`` Click group + ``report`` subcommand."""

from __future__ import annotations

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def parse_endpoint(spec: str) -> tuple[str, str]:
    """``"name=dsn"`` to ``(name, dsn)``.

    A NAME is required rather than derived from the DSN, and that is the
    point of the syntax: a report saying "written to A" is unreadable if A
    is a connection string, and two hosts serving 127.0.0.1:55432 through
    different tunnels produce identical DSNs. The name is what the operator
    reads, so the caller has to say it.

    Splits on the FIRST ``=`` only, because a libpq DSN legitimately
    contains them (``host=x port=y``).
    """
    name, sep, dsn = spec.partition("=")
    if not sep or not name.strip() or not dsn.strip():
        raise ValueError(
            f"expected NAME=DSN, got {spec!r} — e.g. "
            "laptop=postgresql://scitex_cards@127.0.0.1:55432/scitex_cards"
        )
    return name.strip(), dsn.strip()


def register_cardsync_commands(main_group: click.Group) -> click.Group:
    """Register ``scitex-dev cardsync`` on the given main group.

    TOP LEVEL, not under ``dev``, by the §13 discriminator: reconciling the
    fleet's card stores is a SciTeX-wide maintenance operation — this tool's
    domain — not scitex-dev's upkeep of itself.
    """

    @main_group.group(
        "cardsync",
        invoke_without_command=True,
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Measure divergence between two fleet card stores.",
            description=(
                "Three hosts each hold a full copy of the card store and "
                "drift apart with nothing reconciling them; on 2026-08-10 "
                "that reached 2,341 differing rows before anyone looked. "
                "This is the periodic look. It is READ-ONLY: the decision "
                "is computed and reported, and nothing is written, because "
                "a card spans 28 derived columns plus three child tables "
                "and that projection belongs to scitex-cards. Verbs: "
                "report (compare two stores and print the verdict counts).",
            ),
            examples=(
                Example(
                    "{prog} cardsync report laptop=$DSN_A compute-04=$DSN_B",
                    "Compare two stores.",
                ),
            ),
        ),
    )
    @click.pass_context
    def cardsync(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())

    _register_report(cardsync)
    return cardsync


def _register_report(cardsync: click.Group) -> None:
    @cardsync.command(
        "report",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Compare two card stores and report what differs.",
            description=(
                "Reads both stores once and decides per card: identical, "
                "one side newer, one side absent, or UNRESOLVED. Absence is "
                "never read as deletion — comparing end states cannot tell "
                "'never reached me' from 'removed there'. Exits 0 even when "
                "the stores differ, because divergence is the normal state "
                "this measures; pass --fail-on-diverged to use it as a "
                "gate.",
            ),
            examples=(
                Example(
                    "{prog} cardsync report laptop=$A compute-04=$B",
                    "Human-readable counts.",
                ),
                Example(
                    "{prog} cardsync report laptop=$A compute-04=$B --json",
                    "Structured, for a cron line that records history.",
                ),
            ),
        ),
    )
    @click.argument("left")
    @click.argument("right")
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit the report as structured JSON.",
    )
    @click.option(
        "--fail-on-diverged",
        is_flag=True,
        default=False,
        help=(
            "Exit non-zero when the stores differ. OFF by default: these "
            "stores differ routinely between reconciliations, so a "
            "non-zero default would cry wolf on every run."
        ),
    )
    def report(left: str, right: str, as_json: bool, fail_on_diverged: bool) -> None:
        from ...cardsync import PgCardStore, reconcile

        try:
            a_name, a_dsn = parse_endpoint(left)
            b_name, b_dsn = parse_endpoint(right)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc

        store_a = PgCardStore(a_name, a_dsn)
        store_b = PgCardStore(b_name, b_dsn)
        result = reconcile(store_a, store_b)

        if as_json:
            import json

            click.echo(
                json.dumps(
                    {
                        "a": a_name,
                        "b": b_name,
                        "inspected": result.inspected,
                        "already_equal": result.already_equal,
                        "would_write_to_a": result.applied_to_a,
                        "would_write_to_b": result.applied_to_b,
                        "unresolved": [
                            {"id": cid, "reason": why}
                            for cid, why in result.unresolved
                        ],
                    }
                )
            )
        else:
            click.echo(f"{a_name} vs {b_name}: {result.describe()}")
            for cid, why in result.unresolved:
                click.echo(f"  UNRESOLVED {cid}: {why}")

        if fail_on_diverged and (result.applied or result.unresolved):
            raise SystemExit(1)


__all__ = ["parse_endpoint", "register_cardsync_commands"]


# EOF
