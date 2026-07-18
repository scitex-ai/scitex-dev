#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fleet PR-expiry primitive — the operator's 3-day PR rule, one implementation.

The operator rule (all repos, NO exceptions): an open PR that has gone
stale (default: older than 3 days by ``createdAt``) is auto-closed. Until
now three agents (scitex-cards, sac, and this repo's operators) hand-rolled
that rule separately; this module is the single primitive they all consume.

Design — split for testability via dependency injection
-------------------------------------------------------
* :func:`find_expiring` is PURE (no I/O): given a list of :class:`PRInfo`,
  a threshold in days, an age basis, and ``now``, it returns the expiring
  subset. This is the trivially unit-testable core.
* :func:`run_expire` is the orchestrator. Its I/O is INJECTED as three
  callables (``list_fn`` / ``write_intent_fn`` / ``close_fn``) defaulting
  to the real gh/scitex-cards adapters below, so tests drive it with real
  in-memory fakes (NO mocks).

Fail-closed invariant (load-bearing — sac's 2026-07-18 incident was a
write-before-close ordering that was luck, not design): in ``--apply``
mode the intent registry write MUST succeed BEFORE any PR is closed. If
``write_intent_fn`` raises OR returns a falsy result, ``run_expire``
raises and NO ``close_fn`` call is ever made. This is a HARD ASSERT, not
a code-ordering convention — see the dedicated fail-closed test.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable


class PRExpireError(RuntimeError):
    """Raised when the expiry run must abort (notably: intent-write failure)."""


@dataclass
class PRInfo:
    """One open pull request, normalised from ``gh pr list --json``.

    ``head_sha`` (the head-ref OID) is captured alongside ``head_ref`` so a
    closed PR can be recovered EXACTLY: closing keeps the branch, and
    branch + SHA pins the precise commit rather than reconstructing intent
    from the title. (scitex-cards refinement, 2026-07-18.)
    """

    number: int
    title: str
    created_at: datetime
    updated_at: datetime
    author: str
    head_ref: str
    url: str
    body: str
    head_sha: str = ""


@dataclass
class ExpireResult:
    """Outcome of a :func:`run_expire` call."""

    repo: str
    examined: int
    expiring: list[PRInfo] = field(default_factory=list)
    mode: str = "dry-run"  # "dry-run" | "apply"
    intent_card_id: str | None = None
    closed: list[int] = field(default_factory=list)

    @property
    def expiring_count(self) -> int:
        return len(self.expiring)


# --------------------------------------------------------------------- #
# PURE core                                                             #
# --------------------------------------------------------------------- #
def find_expiring(
    prs: list[PRInfo], days: int, by: str, now: datetime
) -> list[PRInfo]:
    """Return the PRs whose age exceeds ``days`` — PURE, no I/O.

    ``by`` selects the age basis: ``"created"`` ages from ``created_at``,
    ``"updated"`` from ``updated_at``. A PR is expiring iff its age is
    STRICTLY GREATER than ``days`` (a PR aged exactly ``days`` is NOT yet
    expiring — the boundary belongs to the young side).
    """
    if by not in ("created", "updated"):
        raise ValueError(f"by must be 'created' or 'updated', got {by!r}")
    threshold = timedelta(days=days)
    out: list[PRInfo] = []
    for pr in prs:
        stamp = pr.created_at if by == "created" else pr.updated_at
        if now - stamp > threshold:
            out.append(pr)
    return out


# --------------------------------------------------------------------- #
# Orchestration (injected I/O)                                          #
# --------------------------------------------------------------------- #
def run_expire(
    repo: str,
    days: int,
    by: str,
    apply: bool,
    *,
    list_fn: Callable[[str], list[PRInfo]] | None = None,
    write_intent_fn: Callable[[str, list[PRInfo]], str] | None = None,
    close_fn: Callable[[PRInfo, str], None] | None = None,
    now: datetime | None = None,
) -> ExpireResult:
    """Compute (and, with ``apply``, enforce) PR expiry for one repo.

    I/O is injected; the defaults are the real adapters below.

    Behaviour:
      * ``list_fn(repo)`` -> the open PRs; :func:`find_expiring` selects.
      * ALWAYS returns the count + list (the caller prints it) BEFORE any
        mutation.
      * dry-run (the DEFAULT, ``apply=False``): stop here, mutate nothing.
      * apply: FAIL-CLOSED. ``write_intent_fn(repo, expiring)`` MUST return
        a truthy card id before any close. If it raises or returns falsy,
        this raises :class:`PRExpireError` and NO close happens. Only after
        a confirmed intent write is ``close_fn`` called per PR.
    """
    list_fn = list_fn or _gh_list_prs
    write_intent_fn = write_intent_fn or _write_intent_card
    close_fn = close_fn or _gh_close_pr
    if now is None:
        now = datetime.now(timezone.utc)

    prs = list_fn(repo)
    expiring = find_expiring(prs, days, by, now)
    result = ExpireResult(
        repo=repo,
        examined=len(prs),
        expiring=list(expiring),
        mode="apply" if apply else "dry-run",
    )

    # Dry-run (default): report only, never mutate.
    if not apply:
        return result

    # Nothing to do — no intent card, no closes.
    if not expiring:
        return result

    # FAIL-CLOSED: persist intent FIRST. A registry-write failure must
    # NEVER be followed by a close. This is a hard guard, not an ordering
    # convention — hence the explicit truthiness assert below.
    try:
        card_id = write_intent_fn(repo, expiring)
    except Exception as exc:  # noqa: BLE001 — any failure aborts before close
        raise PRExpireError(
            f"intent registry write failed for {repo!r}; aborting before any "
            f"close (fail-closed): {exc}"
        ) from exc

    if not card_id:
        raise PRExpireError(
            f"intent registry write for {repo!r} returned a falsy card id "
            f"({card_id!r}); aborting before any close (fail-closed)"
        )

    result.intent_card_id = card_id

    # Only now — with a confirmed-successful intent write — do we close.
    comment = _close_comment(card_id, days, by)
    for pr in expiring:
        close_fn(pr, comment)
        result.closed.append(pr.number)

    return result


def _close_comment(card_id: str, days: int, by: str) -> str:
    """Comment left on each closed PR — points back at the intent card."""
    return (
        f"Auto-closed by `scitex-dev ecosystem pr expire`: open > {days}d "
        f"(by {by}), per the fleet 3-day PR-expiry rule. Intent captured in "
        f"registry card `{card_id}` (branch + head SHA recorded — reopen or "
        f"re-push from there if this matters)."
    )


# --------------------------------------------------------------------- #
# REAL I/O adapters (the injected defaults)                             #
# --------------------------------------------------------------------- #
def _parse_iso(stamp: str) -> datetime:
    """Parse a gh ISO-8601 timestamp (``...Z``) to a tz-aware datetime."""
    if stamp.endswith("Z"):
        stamp = stamp[:-1] + "+00:00"
    dt = datetime.fromisoformat(stamp)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _gh_list_prs(repo: str) -> list[PRInfo]:
    """Open PRs for ``repo`` via ``gh pr list`` -> list[PRInfo].

    ``repo`` is anything ``gh -R`` accepts (``owner/name`` or a URL).
    """
    proc = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "-R",
            repo,
            "--state",
            "open",
            "--json",
            "number,title,createdAt,updatedAt,author,headRefName,headRefOid,url,body",
            "--limit",
            "200",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        raise PRExpireError(
            f"`gh pr list` failed for {repo!r} (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:500]}"
        )
    raw = json.loads(proc.stdout or "[]")
    out: list[PRInfo] = []
    for item in raw:
        author = item.get("author") or {}
        out.append(
            PRInfo(
                number=int(item["number"]),
                title=item.get("title", ""),
                created_at=_parse_iso(item["createdAt"]),
                updated_at=_parse_iso(item["updatedAt"]),
                author=author.get("login", "") if isinstance(author, dict) else str(author),
                head_ref=item.get("headRefName", ""),
                url=item.get("url", ""),
                body=item.get("body", "") or "",
                head_sha=item.get("headRefOid", ""),
            )
        )
    return out


def _gh_close_pr(pr: PRInfo, comment: str) -> None:
    """Close one PR via ``gh pr close`` with an explanatory comment.

    The PR's repo is taken from its URL so a single close targets the
    right repo even across an ``--all`` sweep.
    """
    repo_slug = _repo_slug_from_url(pr.url)
    argv = ["gh", "pr", "close", str(pr.number)]
    if repo_slug:
        argv += ["-R", repo_slug]
    argv += ["--comment", comment]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise PRExpireError(
            f"`gh pr close {pr.number}` failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()[:500]}"
        )


def _repo_slug_from_url(url: str) -> str:
    """``https://github.com/owner/name/pull/12`` -> ``owner/name`` ("" if unparseable)."""
    if not url:
        return ""
    marker = "github.com/"
    idx = url.find(marker)
    if idx < 0:
        return ""
    tail = url[idx + len(marker) :]
    parts = tail.split("/")
    if len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return ""


def _intent_body(repo: str, expiring: list[PRInfo]) -> str:
    """Human-readable body listing every expiring PR (the recovery record)."""
    lines = [
        f"PR-expiry intent registry for `{repo}` — "
        f"{len(expiring)} PR(s) slated for auto-close.",
        "",
        "Each PR is recorded with branch + head SHA so a close that turns "
        "out to matter can be recovered EXACTLY (the branch survives close).",
        "",
    ]
    for pr in expiring:
        summary = (pr.body or "").strip().splitlines()
        first = summary[0][:120] if summary else ""
        lines.append(
            f"- #{pr.number} \"{pr.title}\" by {pr.author or '?'}\n"
            f"    created: {pr.created_at.isoformat()}  updated: {pr.updated_at.isoformat()}\n"
            f"    branch: {pr.head_ref}  head_sha: {pr.head_sha or '?'}\n"
            f"    url: {pr.url}"
            + (f"\n    summary: {first}" if first else "")
        )
    return "\n".join(lines)


def _write_intent_card(repo: str, expiring: list[PRInfo]) -> str:
    """Persist ONE intent-registry card listing every expiring PR; return its id.

    Prefers the in-process ``scitex_cards.add_task`` API; falls back to the
    ``scitex-todo`` CLI when the library is unavailable. RAISES on any
    failure so :func:`run_expire` fail-closes before any PR is closed.
    """
    slug = repo.replace("/", "-").replace(" ", "-")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    card_id = f"pr-expire-intent-{slug}-{stamp}"
    title = f"[pr-expire] intent: {len(expiring)} PR(s) in {repo}"
    note = _intent_body(repo, expiring)

    try:
        import scitex_cards  # type: ignore

        task = scitex_cards.add_task(
            id=card_id,
            title=title,
            status="done",
            note=note,
            created_by="scitex-dev",
        )
        # Prefer the id the writer actually persisted, if it echoes one.
        if isinstance(task, dict):
            return task.get("id", card_id) or card_id
        return card_id
    except ImportError:
        pass  # fall through to the CLI path

    # CLI fallback: shell `scitex-todo add-task`.
    proc = subprocess.run(
        [
            "scitex-todo",
            "add-task",
            "--id",
            card_id,
            "--title",
            title,
            "--status",
            "done",
            "--note",
            note,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        raise PRExpireError(
            f"intent card write via scitex-todo CLI failed (exit "
            f"{proc.returncode}): {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    return card_id


# EOF
