#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/ci/_mergeable_cmd.py
"""``scitex-dev ci verify`` — a merge verdict a script can gate on.

Exit codes are the interface; the printed text is for the human who has to
fix it::

     0  ready              every check on the CURRENT head passed
    10  not ready          at least one named reason, one line each
    11  cannot determine   the question could not be answered

    (1 and 2 are the FRAMEWORK's — generic failure and usage error. Click
     exits 2 for an unknown subcommand before this file runs.)

11 is deliberately distinct from 10. "No" and "I could not tell" call for
different actions, and collapsing them is how a tool starts lying: fold
unknown into no and people disable it, fold it into yes and it ships the bug.

WHY THE DOMAIN CODES START AT 10, measured 2026-08-09: they were 2 and 3.
A venv holding a scitex-dev older than this command made Click answer
``No such command 'verify'`` with exit 2 — and the gating hook read that as
the domain answer, reporting "the pull request is NOT ready to merge" about
a pull request green on all seven checks. See :mod:`scitex_dev.ci._exit_codes`,
where the collision is now checked at import rather than warned about.
"""

from __future__ import annotations

import json as _json

import click

from ..._ecosystem.help_spec import CliHelp, Example, SpecCommand


def register_ci_commands(main_group: click.Group) -> None:
    """Register ``scitex-dev ci ...`` on the given main group."""

    @main_group.group("ci", cls=click.Group, help="CI verdicts and CI plumbing.")
    def ci_group() -> None:
        """Commands that answer questions about CI state."""

    # `verify`, not `mergeable`: the CLI audit rejects an adjective as a verb,
    # and it is right to. Every other leaf in this CLI reads noun-verb, and
    # `ci mergeable 521` parses as a claim ("this is mergeable") rather than
    # an instruction — which is the opposite of what the command does, since
    # its whole job is to REFUSE that claim when it cannot be substantiated.
    @ci_group.command(
        "verify",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Verify PR is actually mergeable, per check, on the current head.",
            description=(
                "Reads PER-CHECK state and compares every check run's commit "
                "against the pull request's CURRENT head, so a green "
                "inherited from an older commit cannot pass. Never reads the "
                "rolled-up summary line, which folds SKIPPING rows into the "
                "pass total and can hide a required check that never ran. "
                "Exit 0 = ready, 10 = not ready (one line per reason), "
                "11 = cannot determine; 1 and 2 stay the framework's generic "
                "failure and usage error. --repo is REQUIRED: a bare PR "
                "number is ambiguous across this fleet's repositories and "
                "has already identified the wrong one."
            ),
            examples=(
                Example(
                    "{prog} ci verify 521 --repo scitex-ai/scitex-dev",
                    "Verdict for one pull request.",
                ),
                Example(
                    "{prog} ci verify 521 --repo scitex-ai/scitex-dev --json",
                    "Machine-readable, for a gating script.",
                ),
            ),
        ),
    )
    @click.argument("pr", type=str)
    @click.option(
        "--repo",
        required=True,
        help="owner/repo. Required — never inferred from the working directory.",
    )
    @click.option(
        "--json",
        "as_json",
        is_flag=True,
        default=False,
        help="Emit the full verdict as JSON.",
    )
    def verify(pr: str, repo: str, as_json: bool) -> None:
        """Decide whether ``--repo``'s pull request ``PR`` may be merged."""
        from ...ci import readiness

        verdict = readiness(pr, repo)
        if as_json:
            click.echo(_json.dumps(verdict.to_dict(), indent=2))
        else:
            click.echo(verdict.render())
        raise SystemExit(verdict.exit_code)


# EOF
