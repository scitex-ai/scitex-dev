#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ecosystem `pr expire` — fleet 3-day PR-expiry primitive.

Thin CLI surface over ``scitex_dev._ecosystem.pr_expire``. All logic
(pure ``find_expiring`` + fail-closed ``run_expire`` + the gh/scitex-cards
adapters) lives in the engine module; this file only wires options,
resolves the target repo(s), prints the count-before-close, and calls
``run_expire``.

Contract (see the engine docstring): dry-run is the DEFAULT; ``--apply``
required to mutate; ``--apply`` is FAIL-CLOSED — the intent registry card
must be written before any PR is closed, or nothing is closed.
"""

from __future__ import annotations

import subprocess

import click

from ...._ecosystem.help_spec import CliHelp, Example, SpecCommand, SpecGroup


def _current_repo_slug() -> str | None:
    """Resolve ``owner/name`` from the current checkout's origin remote."""
    try:
        proc = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Fallback: parse `git remote get-url origin`.
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    # git@github.com:owner/name.git  |  https://github.com/owner/name.git
    slug = out
    if slug.startswith("git@") and ":" in slug:
        slug = slug.split(":", 1)[1]
    else:
        marker = "github.com/"
        idx = slug.find(marker)
        if idx >= 0:
            slug = slug[idx + len(marker) :]
    if slug.endswith(".git"):
        slug = slug[: -len(".git")]
    return slug or None


def _all_repo_slugs() -> list[str]:
    """Every non-archived ecosystem package's ``github_repo`` slug."""
    from ...._ecosystem._core import ECOSYSTEM

    slugs: list[str] = []
    for _pkg, info in ECOSYSTEM.items():
        if info.get("archived"):
            continue
        slug = info.get("github_repo")
        if slug:
            slugs.append(slug)
    return slugs


def register(ecosystem):
    @ecosystem.group(
        "pr",
        cls=SpecGroup,
        help_spec=CliHelp(
            summary="Pull-request fleet operations (expiry, ...).",
            examples=(
                Example("{prog} ecosystem pr expire", "Dry-run 3-day expiry, current repo."),
                Example("{prog} ecosystem pr expire --all", "Dry-run across the whole fleet."),
            ),
        ),
    )
    def pr():
        pass

    @pr.command(
        "expire",
        cls=SpecCommand,
        help_spec=CliHelp(
            summary="Close open PRs older than --days (default 3) — the fleet rule.",
            description=(
                "Enforces the operator's 3-day PR-expiry rule (all repos, "
                "no exceptions). Default = DRY-RUN: lists the expiring PRs "
                "and a count, mutates NOTHING. --apply is FAIL-CLOSED: it "
                "first writes ONE intent-registry card capturing every "
                "expiring PR (number, title, author, created_at, branch + "
                "head SHA, body summary) so a close that matters is "
                "recoverable EXACTLY; only after that write succeeds are the "
                "PRs closed. If the intent write fails, NOTHING is closed. "
                "--all sweeps every non-archived ecosystem repo; otherwise "
                "the current repo (from origin) or --repo. --by created "
                "(default) ages from createdAt; --by updated from updatedAt."
            ),
            examples=(
                Example("{prog} ecosystem pr expire", "Dry-run, current repo, 3 days."),
                Example("{prog} ecosystem pr expire --days 0", "List every open PR (dry-run)."),
                Example("{prog} ecosystem pr expire --apply", "Close (fail-closed intent first)."),
                Example("{prog} ecosystem pr expire --all --by updated", "Fleet-wide, by updatedAt."),
            ),
        ),
    )
    @click.option("--days", default=3, show_default=True, type=int, help="Age threshold in days.")
    @click.option("--repo", "repo", default=None, help="Target repo (owner/name). Default: current repo from origin.")
    @click.option("--all", "do_all", is_flag=True, help="Every non-archived ecosystem repo.")
    @click.option(
        "--by",
        type=click.Choice(["created", "updated"]),
        default="created",
        show_default=True,
        help="Age basis: createdAt (default) or updatedAt.",
    )
    @click.option("--apply/--dry-run", "apply", default=False, help="Actually close (default: dry-run).")
    @click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
    def pr_expire(days, repo, do_all, by, apply, as_json):
        import json as _json

        from ...._ecosystem.pr_expire import ExpireResult, run_expire

        if do_all and repo:
            raise click.UsageError("--all and --repo are mutually exclusive.")

        if do_all:
            repos = _all_repo_slugs()
            if not repos:
                raise click.ClickException("no ecosystem repos found in the registry.")
        else:
            target = repo or _current_repo_slug()
            if not target:
                raise click.ClickException(
                    "could not resolve current repo from origin; pass --repo owner/name."
                )
            repos = [target]

        results: list[ExpireResult] = []
        for r in repos:
            results.append(run_expire(r, days=days, by=by, apply=apply))

        if as_json:
            click.echo(_json.dumps([_result_dict(res) for res in results], indent=2, default=str))
            return

        _render(results, days=days, by=by, apply=apply)

    def _result_dict(res) -> dict:
        return {
            "repo": res.repo,
            "examined": res.examined,
            "expiring_count": res.expiring_count,
            "mode": res.mode,
            "intent_card_id": res.intent_card_id,
            "closed": res.closed,
            "expiring": [
                {
                    "number": pr.number,
                    "title": pr.title,
                    "author": pr.author,
                    "created_at": pr.created_at.isoformat(),
                    "updated_at": pr.updated_at.isoformat(),
                    "head_ref": pr.head_ref,
                    "head_sha": pr.head_sha,
                    "url": pr.url,
                }
                for pr in res.expiring
            ],
        }

    def _render(results, *, days, by, apply):
        verb = "Closed" if apply else "Would close"
        total = 0
        for res in results:
            # COUNT + list BEFORE anything else (mirrors the engine order).
            click.echo(
                f"{res.repo}: {res.expiring_count} of {res.examined} open PR(s) "
                f"expiring (> {days}d by {by})"
            )
            for pr in res.expiring:
                age_note = pr.created_at.isoformat() if by == "created" else pr.updated_at.isoformat()
                click.echo(
                    f"  · #{pr.number} {pr.title}  ({pr.author}, {by}={age_note}, "
                    f"branch={pr.head_ref}@{(pr.head_sha or '?')[:12]})"
                )
            if apply and res.intent_card_id:
                click.echo(f"  intent card: {res.intent_card_id}")
            if apply and res.closed:
                click.echo(f"  closed: {', '.join('#' + str(n) for n in res.closed)}")
            total += res.expiring_count

        click.echo("")
        click.echo(
            f"{verb}: {total} PR(s) across {len(results)} repo(s).", err=True
        )
        if not apply:
            click.echo("Dry-run — re-run with --apply to close (intent captured first).", err=True)
