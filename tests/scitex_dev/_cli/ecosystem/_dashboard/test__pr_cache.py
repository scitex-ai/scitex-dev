"""Tests for the open-PR CI dedup cache (real SQLite tmp DB, no mocks)."""

from scitex_dev._cli.ecosystem._dashboard import _pr_cache


def _row(repo="scitex-io", pr=1, check="audit", state="failed"):
    return {
        "repo": repo,
        "pr_number": pr,
        "check_name": check,
        "state": state,
        "head_sha": "sha1",
        "pr_title": "title",
        "pr_updated_at": None,
    }


def test_upsert_then_query_returns_the_row(tmp_path):
    # Arrange
    conn = _pr_cache.connect(tmp_path / "c.db")
    # Act
    _pr_cache.upsert_checks(conn, [_row()])
    # Assert
    assert len(_pr_cache.query(conn)) == 1


def test_upsert_same_key_dedups_in_place(tmp_path):
    # Arrange
    conn = _pr_cache.connect(tmp_path / "c.db")
    _pr_cache.upsert_checks(conn, [_row(state="failed")])
    # Act
    _pr_cache.upsert_checks(conn, [_row(state="running")])
    # Assert
    assert conn.execute("SELECT COUNT(*) AS c FROM pr_checks").fetchone()["c"] == 1


def test_query_default_excludes_success(tmp_path):
    # Arrange
    conn = _pr_cache.connect(tmp_path / "c.db")
    _pr_cache.upsert_checks(
        conn, [_row(check="a", state="success"), _row(check="b", state="failed")]
    )
    # Act
    names = [r["check_name"] for r in _pr_cache.query(conn)]
    # Assert
    assert names == ["b"]


def test_query_state_filter_selects_one(tmp_path):
    # Arrange
    conn = _pr_cache.connect(tmp_path / "c.db")
    _pr_cache.upsert_checks(
        conn, [_row(check="a", state="running"), _row(check="b", state="failed")]
    )
    # Act
    names = [r["check_name"] for r in _pr_cache.query(conn, states=["running"])]
    # Assert
    assert names == ["a"]


def test_query_repo_glob_filters(tmp_path):
    # Arrange
    conn = _pr_cache.connect(tmp_path / "c.db")
    _pr_cache.upsert_checks(conn, [_row(repo="scitex-io"), _row(repo="figrecipe")])
    # Act
    repos = {r["repo"] for r in _pr_cache.query(conn, repo_glob="scitex-*")}
    # Assert
    assert repos == {"scitex-io"}


def test_reconcile_drops_closed_prs(tmp_path):
    # Arrange
    conn = _pr_cache.connect(tmp_path / "c.db")
    _pr_cache.upsert_checks(conn, [_row(pr=1), _row(pr=2)])
    # Act
    dropped = _pr_cache.reconcile(conn, {("scitex-io", 1)})
    # Assert
    assert dropped == 1
