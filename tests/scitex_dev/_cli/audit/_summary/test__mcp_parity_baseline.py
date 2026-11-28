"""Tests for `_mcp_parity_baseline` — the §6 shrink-only parity ratchet.

Real files under `tmp_path` and real name sets; no mocks. End-to-end runs
of the auditor live in `tests/integration/test_mcp_parity_ratchet.py`.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.audit._summary._mcp_parity_baseline import (
    MCP_PARITY_BASELINE_RELPATH,
    MalformedParityBaseline,
    ParityBaseline,
    format_backlog_notice,
    load_parity_baseline,
    ratchet_violations,
    write_parity_baseline,
)


def _baseline(tmp_path, entries):
    return ParityBaseline(
        path=tmp_path / MCP_PARITY_BASELINE_RELPATH, missing=frozenset(entries)
    )


class TestLoadAndWrite:
    def test_absent_file_means_no_ratchet(self, tmp_path):
        # Arrange
        root = tmp_path
        # Act
        loaded = load_parity_baseline(root)
        # Assert
        assert loaded is None

    def test_no_audited_tree_means_no_ratchet(self):
        # Arrange
        root = None
        # Act
        loaded = load_parity_baseline(root)
        # Assert
        assert loaded is None

    def test_written_baseline_round_trips(self, tmp_path):
        # Arrange
        write_parity_baseline(tmp_path, {"write_status", "list_items"})
        # Act
        loaded = load_parity_baseline(tmp_path)
        # Assert
        assert loaded.missing == frozenset({"write_status", "list_items"})

    def test_written_entries_are_sorted_for_stable_diffs(self, tmp_path):
        # Arrange
        path = write_parity_baseline(tmp_path, {"zeta", "alpha"})
        # Act
        text = path.read_text()
        # Assert
        assert text.index("- alpha") < text.index("- zeta")

    @pytest.mark.parametrize(
        "body",
        [
            "missing_mcp_tools: [a]\n",  # no version
            "version: 2\nmissing_mcp_tools: [a]\n",  # unknown version
            "version: 1\nmissing_mcp_tools: a\n",  # not a list
            "version: 1\nmissing_mcp_tools: [1]\n",  # not names
            "version: 1\nmissing_mcp_tools: [a, a]\n",  # duplicates
            "version: 1\nmissing_mcp_tools: [a\n",  # invalid YAML
            "- a\n",  # not a mapping
        ],
    )
    def test_malformed_file_raises_instead_of_suppressing(self, tmp_path, body):
        # Arrange
        path = tmp_path / MCP_PARITY_BASELINE_RELPATH
        path.parent.mkdir(parents=True)
        path.write_text(body)
        # Act
        def load():
            return load_parity_baseline(tmp_path)

        # Assert
        with pytest.raises(MalformedParityBaseline, match="mcp-parity-baseline.yaml"):
            load()


class TestRatchet:
    def test_recorded_backlog_alone_is_not_a_violation(self, tmp_path):
        # Arrange
        baseline = _baseline(tmp_path, {"a", "b"})
        # Act
        violations = ratchet_violations("pkg", {"a", "b"}, baseline)
        # Assert
        assert violations == []

    def test_new_missing_api_is_a_violation_naming_it(self, tmp_path):
        # Arrange
        baseline = _baseline(tmp_path, {"a"})
        # Act
        violations = ratchet_violations("pkg", {"a", "new_api"}, baseline)
        # Assert
        assert [("§6", "['new_api']" in v.message) for v in violations] == [
            ("§6", True)
        ]

    def test_closed_gap_still_listed_is_a_violation_naming_it(self, tmp_path):
        # Arrange
        baseline = _baseline(tmp_path, {"a", "closed"})
        # Act
        violations = ratchet_violations("pkg", {"a"}, baseline)
        # Assert
        assert [("§6", "['closed']" in v.message) for v in violations] == [("§6", True)]

    def test_new_and_stale_are_reported_separately(self, tmp_path):
        # Arrange
        baseline = _baseline(tmp_path, {"closed"})
        # Act
        violations = ratchet_violations("pkg", {"new_api"}, baseline)
        # Assert
        assert len(violations) == 2

    def test_backlog_notice_counts_only_recorded_missing(self, tmp_path):
        # Arrange
        baseline = _baseline(tmp_path, {"a", "b", "closed"})
        # Act
        notice = format_backlog_notice("pkg", {"a", "b", "new_api"}, baseline, 10)
        # Assert
        assert "backlog 2/10" in notice
