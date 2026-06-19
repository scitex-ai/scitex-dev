"""``ecosystem dashboard prs`` — open-PR CI backlog from the dedup cache.

Complements the dashboard's per-repo *develop*-health view with the per-PR
*backlog* view (operator design 2026-06-20): which open PRs have failing /
running / pending CI, fleet-wide. Reads the SQLite cache (:mod:`_pr_cache`)
so a view costs zero API calls; ``--refresh`` re-fetches via :mod:`_pr_state`.
"""

from __future__ import annotations

from collections import defaultdict

import click

from .._dashboard import _pr_cache, _pr_state


def _ecosystem_repos() -> list[str]:
    """GitHub repo basenames for every ecosystem package (from ECOSYSTEM)."""
    try:
        from scitex_dev._ecosystem._core import ECOSYSTEM
    except ImportError:
        return []
    out: list[str] = []
    for pkg, info in dict(ECOSYSTEM).items():
        gh = ((info or {}).get("github_repo") or "").split("/")[-1]
        out.append(gh or pkg)
    return sorted({r for r in out if r})


def register_prs(dashboard) -> None:
    """Attach the ``prs`` subcommand to the dashboard click group."""

    @dashboard.command("prs")
    @click.option(
        "--state",
        "-s",
        type=click.Choice(["failed", "running", "pending", "all"]),
        default="all",
        show_default=True,
        help="Filter by check state.",
    )
    @click.option(
        "--repo",
        "-r",
        "repo_glob",
        default=None,
        help="SQLite GLOB over repo name, e.g. 'scitex-*'.",
    )
    @click.option(
        "--refresh/--no-refresh",
        default=False,
        help="Re-fetch from GitHub into the cache before showing.",
    )
    @click.option("--owner", default="ywatanabe1989", show_default=True)
    def prs(state: str, repo_glob: str | None, refresh: bool, owner: str) -> None:
        """Open-PR CI backlog, served from the dedup SQLite cache.

        \b
        The cache means a view costs no API calls — refresh periodically (cron)
        or pass --refresh. Completed-success checks are filtered out.
        """
        conn = _pr_cache.connect()
        try:
            if refresh:
                summary = _pr_state.refresh(conn, _ecosystem_repos(), owner=owner)
                click.echo(
                    f"refreshed {summary['repos']} repos: {summary['prs']} open PRs, "
                    f"{summary['checks']} checks cached, {summary['dropped']} stale dropped"
                )
            states = None if state == "all" else [state]
            rows = _pr_cache.query(conn, states=states, repo_glob=repo_glob)
            fetched = _pr_cache.last_fetched_at(conn)
        finally:
            conn.close()

        grouped: dict[tuple[str, int, str], list[tuple[str, str]]] = defaultdict(list)
        for row in rows:
            grouped[(row["repo"], row["pr_number"], row["pr_title"] or "")].append(
                (row["state"], row["check_name"])
            )
        click.echo(
            f"=== PR CI backlog (filter={state}) — {len(grouped)} PRs "
            f"| cache fetched: {fetched or 'never — run with --refresh'} ==="
        )
        for (repo, num, title), checks in sorted(grouped.items()):
            tags = ", ".join(f"{st[0].upper()}:{name}" for st, name in checks)
            click.echo(f"  {repo} #{num} [{title[:46]}] -> {tags}")
        if not grouped:
            click.echo("  (empty — run: scitex-dev ecosystem dashboard prs --refresh)")
