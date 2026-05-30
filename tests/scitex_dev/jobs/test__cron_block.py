#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the idempotent BEGIN/END managed crontab block."""

from __future__ import annotations

from scitex_dev.jobs import JobSpec
from scitex_dev.jobs import _cron_block as cb


def _jobs():
    return [
        JobSpec(
            name="a.one", schedule="*/5 * * * *", command="run one", description="d1"
        ),
        JobSpec(
            name="b.two", schedule="0 * * * *", command="run two", description="d2"
        ),
    ]


def test_render_block_has_begin_marker():
    # Arrange
    jobs = _jobs()
    # Act
    text = cb.render_block(jobs)
    # Assert
    assert cb.BLOCK_BEGIN in text


def test_render_block_has_end_marker():
    # Arrange
    jobs = _jobs()
    # Act
    text = cb.render_block(jobs)
    # Assert
    assert cb.BLOCK_END in text


def test_render_block_line_count_matches_jobs():
    # Arrange
    jobs = _jobs()
    # Act
    job_lines = [
        ln for ln in cb.render_block(jobs).splitlines() if cb.LINE_MARKER_PREFIX in ln
    ]
    # Assert
    assert len(job_lines) == 2


def test_upsert_block_into_empty_crontab():
    # Arrange
    jobs = _jobs()
    # Act
    result = cb.upsert_block("", jobs)
    # Assert
    assert result.count(cb.BLOCK_BEGIN) == 1


def test_upsert_block_is_idempotent_no_duplicate_blocks():
    # Arrange
    jobs = _jobs()
    once = cb.upsert_block("", jobs)
    # Act
    twice = cb.upsert_block(once, jobs)
    # Assert
    assert twice.count(cb.BLOCK_BEGIN) == 1


def test_upsert_block_idempotent_output_is_stable():
    # Arrange
    jobs = _jobs()
    once = cb.upsert_block("", jobs)
    # Act
    twice = cb.upsert_block(once, jobs)
    # Assert
    assert twice == once


def test_upsert_block_preserves_unrelated_lines():
    # Arrange
    existing = "# user comment\n0 0 * * * /usr/bin/backup\n"
    # Act
    result = cb.upsert_block(existing, _jobs())
    # Assert
    assert "/usr/bin/backup" in result


def test_upsert_block_empty_jobs_removes_block():
    # Arrange
    seeded = cb.upsert_block("# keep me\n", _jobs())
    # Act
    cleared = cb.upsert_block(seeded, [])
    # Assert
    assert cb.BLOCK_BEGIN not in cleared


def test_remove_line_drops_named_line():
    # Arrange
    seeded = cb.upsert_block("", _jobs())
    # Act
    new, _ = cb.remove_line(seeded, "a.one")
    # Assert
    assert "a.one" not in new


def test_remove_line_returns_removed_count():
    # Arrange
    seeded = cb.upsert_block("", _jobs())
    # Act
    _, removed = cb.remove_line(seeded, "a.one")
    # Assert
    assert removed == 1


def test_remove_last_line_collapses_block():
    # Arrange
    single = cb.upsert_block(
        "",
        [JobSpec(name="x.solo", schedule="* * * * *", command="c", description="d")],
    )
    # Act
    new, _ = cb.remove_line(single, "x.solo")
    # Assert
    assert cb.BLOCK_BEGIN not in new


# EOF
