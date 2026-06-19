"""Fetch open-PR CI check states across the ecosystem, into the cache.

One GraphQL query PER REPO pulls every open PR's latest-commit check rollup;
states are classified and written to :mod:`_pr_cache` (UPSERT = dedup). Reads
then serve from the cache, so the live API cost is one periodic refresh, not
one-per-view (operator's rate-limit directive 2026-06-20).

GraphQL is used over REST because one query returns a PR's *every* check at
once (the dashboard's develop-health path proved the pattern); per-repo keeps
each query small (no node-limit risk from aliasing 70 repos × 30 PRs × 80
checks into one document).
"""

from __future__ import annotations

import json
import subprocess

from . import _pr_cache

_GQL = """
query($owner:String!, $name:String!) {
  repository(owner:$owner, name:$name) {
    pullRequests(states:OPEN, first:30, orderBy:{field:UPDATED_AT, direction:DESC}) {
      nodes {
        number title
        commits(last:1) { nodes { commit { oid statusCheckRollup {
          contexts(first:80) { nodes {
            __typename
            ... on CheckRun { name status conclusion }
            ... on StatusContext { context state }
          }}
        }}}}
      }
    }
  }
}
"""

_FAIL = {
    "FAILURE",
    "TIMED_OUT",
    "CANCELLED",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
    "STALE",
    "ERROR",
}
_RUNNING = {"QUEUED", "IN_PROGRESS", "WAITING", "PENDING", "REQUESTED"}
_OK = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def _classify(node: dict) -> tuple[str, str] | None:
    """Map a check node to ``(state, name)`` where state is
    failed | running | pending | success; None if unrecognised."""
    if node.get("__typename") == "CheckRun":
        status, concl, name = (
            node.get("status"),
            node.get("conclusion"),
            node.get("name", "?"),
        )
        if status in _RUNNING:
            return ("running", name)
        if status == "COMPLETED":
            if concl in _FAIL:
                return ("failed", name)
            if concl in _OK:
                return ("success", name)
        return None
    # StatusContext (legacy: CLAssistant, codecov, readthedocs…)
    state, ctx = node.get("state"), node.get("context", "?")
    if state in ("FAILURE", "ERROR"):
        return ("failed", ctx)
    if state in ("PENDING", "EXPECTED"):
        return ("pending", ctx)
    if state == "SUCCESS":
        return ("success", ctx)
    return None


def _gh_graphql(owner: str, repo: str) -> dict | None:
    try:
        proc = subprocess.run(
            [
                "gh",
                "api",
                "graphql",
                "-f",
                f"query={_GQL}",
                "-F",
                f"owner={owner}",
                "-F",
                f"name={repo}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def fetch_repo(owner: str, repo: str) -> tuple[list[dict], set[tuple[str, int]]]:
    """Return (check-rows, open-pr-keys) for one repo. Empty on API failure."""
    data = _gh_graphql(owner, repo)
    rows: list[dict] = []
    keys: set[tuple[str, int]] = set()
    if not data or not data.get("data"):
        return rows, keys
    rp = (data["data"] or {}).get("repository")
    if not rp:
        return rows, keys
    for pr in rp["pullRequests"]["nodes"]:
        commits = pr["commits"]["nodes"]
        if not commits:
            continue
        commit = commits[0]["commit"]
        roll = commit.get("statusCheckRollup")
        if not roll:
            continue
        keys.add((repo, pr["number"]))
        for node in roll["contexts"]["nodes"]:
            classified = _classify(node)
            if not classified:
                continue
            state, name = classified
            rows.append(
                {
                    "repo": repo,
                    "pr_number": pr["number"],
                    "check_name": name,
                    "state": state,
                    "head_sha": commit.get("oid"),
                    "pr_title": (pr.get("title") or "")[:80],
                    "pr_updated_at": None,
                }
            )
    return rows, keys


def refresh(conn, repos: list[str], owner: str = "ywatanabe1989") -> dict:
    """Refresh the cache for ``repos``: fetch, UPSERT, reconcile closed PRs.

    Returns a summary dict {repos, prs, checks, dropped}.
    """
    all_rows: list[dict] = []
    all_keys: set[tuple[str, int]] = set()
    for repo in repos:
        rows, keys = fetch_repo(owner, repo)
        all_rows.extend(rows)
        all_keys |= keys
    _pr_cache.upsert_checks(conn, all_rows)
    dropped = _pr_cache.reconcile(conn, all_keys)
    return {
        "repos": len(repos),
        "prs": len(all_keys),
        "checks": len(all_rows),
        "dropped": dropped,
    }
