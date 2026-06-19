"""SQLite cache for open-PR CI check states — dedup + fewer API requests.

The fleet PR-backlog view (``ecosystem dashboard prs``) must not hammer the
GitHub API on every invocation. Instead a periodic refresh writes check states
here once, and every read serves from this DB (operator directive 2026-06-20:
"cache once-retrieved or periodically-acquired data into a database with dedup").

Dedup is structural: the primary key is ``(repo, pr_number, check_name)`` and
writes are UPSERTs, so a check has exactly ONE row that is updated in place —
rows never accumulate across refreshes. ``reconcile`` drops rows for PRs that
are no longer open (merged/closed) so the cache tracks the live backlog.

Layout: ``$SCITEX_DIR/dev/runtime/ci-pr-cache.db``
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pr_checks (
    repo          TEXT    NOT NULL,
    pr_number     INTEGER NOT NULL,
    check_name    TEXT    NOT NULL,
    state         TEXT    NOT NULL,   -- failed | running | pending | success
    head_sha      TEXT,
    pr_title      TEXT,
    pr_updated_at TEXT,
    fetched_at    TEXT    NOT NULL,
    PRIMARY KEY (repo, pr_number, check_name)
);
CREATE INDEX IF NOT EXISTS idx_pr_checks_state ON pr_checks(state);
CREATE INDEX IF NOT EXISTS idx_pr_checks_repo  ON pr_checks(repo);
"""


def _scitex_dir() -> Path:
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def cache_db_path() -> Path:
    """Path to the SQLite cache DB (override the parent via ``$SCITEX_DIR``)."""
    return _scitex_dir() / "dev" / "runtime" / "ci-pr-cache.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the cache DB with the schema applied.

    ``db_path`` is a seam for tests (pass a tmp file); defaults to
    :func:`cache_db_path`.
    """
    path = db_path or cache_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def upsert_checks(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """UPSERT check rows (dedup on ``(repo, pr_number, check_name)``).

    Each row dict needs: repo, pr_number, check_name, state, head_sha,
    pr_title, pr_updated_at. ``fetched_at`` is stamped here. Returns the count.
    """
    if not rows:
        return 0
    now = _utcnow_iso()
    payload = [
        {
            "repo": r["repo"],
            "pr_number": r["pr_number"],
            "check_name": r["check_name"],
            "state": r["state"],
            "head_sha": r.get("head_sha"),
            "pr_title": r.get("pr_title"),
            "pr_updated_at": r.get("pr_updated_at"),
            "fetched_at": now,
        }
        for r in rows
    ]
    conn.executemany(
        """
        INSERT INTO pr_checks
            (repo, pr_number, check_name, state, head_sha, pr_title, pr_updated_at, fetched_at)
        VALUES
            (:repo, :pr_number, :check_name, :state, :head_sha, :pr_title, :pr_updated_at, :fetched_at)
        ON CONFLICT(repo, pr_number, check_name) DO UPDATE SET
            state         = excluded.state,
            head_sha      = excluded.head_sha,
            pr_title      = excluded.pr_title,
            pr_updated_at = excluded.pr_updated_at,
            fetched_at    = excluded.fetched_at
        """,
        payload,
    )
    conn.commit()
    return len(payload)


def reconcile(conn: sqlite3.Connection, open_pr_keys: set[tuple[str, int]]) -> int:
    """Delete cached rows for PRs not in ``open_pr_keys`` (merged/closed).

    Keeps the cache tracking the LIVE backlog. Returns rows deleted.
    """
    existing = {
        (row["repo"], row["pr_number"])
        for row in conn.execute("SELECT DISTINCT repo, pr_number FROM pr_checks")
    }
    stale = [key for key in existing if key not in open_pr_keys]
    if stale:
        conn.executemany(
            "DELETE FROM pr_checks WHERE repo = ? AND pr_number = ?", stale
        )
        conn.commit()
    return len(stale)


def query(
    conn: sqlite3.Connection,
    *,
    states: list[str] | None = None,
    repo_glob: str | None = None,
) -> list[sqlite3.Row]:
    """Read the cached backlog, filtered. No states → all non-success checks.

    ``states`` filters by check state; ``repo_glob`` is a SQLite GLOB pattern
    (e.g. ``scitex-*``). Results are ordered repo, then PR number.
    """
    sql = (
        "SELECT repo, pr_number, check_name, state, pr_title, fetched_at FROM pr_checks"
    )
    clauses: list[str] = []
    params: list[object] = []
    if states:
        clauses.append(f"state IN ({','.join('?' * len(states))})")
        params.extend(states)
    else:
        clauses.append("state != 'success'")
    if repo_glob:
        clauses.append("repo GLOB ?")
        params.append(repo_glob)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY repo, pr_number, check_name"
    return list(conn.execute(sql, params))


def last_fetched_at(conn: sqlite3.Connection) -> str | None:
    """Most recent ``fetched_at`` across the cache (freshness signal)."""
    row = conn.execute("SELECT MAX(fetched_at) AS m FROM pr_checks").fetchone()
    return row["m"] if row else None
