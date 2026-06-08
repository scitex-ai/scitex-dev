"""Tests for ``scitex_dev.ci.runner._status``."""

from __future__ import annotations

from scitex_dev.ci.runner._status import XdistConstants, _compute_xdist_n, _xdist_tuning_table


class TestXdistConstants:
    """Test the xdist tuning constants are well-formed."""

    def test_bins_have_two_entries(self):
        assert len(XdistConstants.BINS) == 2
        assert XdistConstants.BINS[0] == (32, 16)
        assert XdistConstants.BINS[1] == (128, 32)

    def test_default_fallback_is_positive(self):
        assert XdistConstants.DEFAULT_FALLBACK == 16
        assert XdistConstants.DEFAULT_FALLBACK > 0


class TestComputeXdistN:
    """Test the adaptive xdist worker count computation."""

    def test_very_few_tests_returns_min_of_bin_and_cap(self):
        # nproc=8 → phys_cap=4, n_tests=10 <= 32 → min(16, 4) = 4
        result = _compute_xdist_n(10, nproc=8)
        assert result == 4

    def test_32_tests_returns_16_capped(self):
        result = _compute_xdist_n(32, nproc=64)
        assert result == 16

    def test_33_tests_returns_32_capped(self):
        result = _compute_xdist_n(64, nproc=64)
        assert result == 32

    def test_128_tests_returns_32_capped(self):
        result = _compute_xdist_n(128, nproc=64)
        assert result == 32

    def test_over_128_returns_phys_cap(self):
        result = _compute_xdist_n(200, nproc=8)
        assert result == 4  # 8 // 2 = 4

    def test_zero_tests_returns_min_of_bin_and_cap(self):
        result = _compute_xdist_n(0, nproc=64)
        assert result == 16

    def test_cap_prevents_exceeding_phys_cap(self):
        # n_tests=50, nproc=4 → phys_cap=2, bin says 32, capped at 2
        result = _compute_xdist_n(50, nproc=4)
        assert result == 2

    def test_single_proc_returns_at_least_1(self):
        result = _compute_xdist_n(10, nproc=1)
        assert result == 1


class TestXdistTuningTable:
    """Test the xdist tuning table generation."""

    def test_returns_three_rows(self):
        table = _xdist_tuning_table()
        assert len(table) == 3

    def test_first_row_is_small_tests(self):
        table = _xdist_tuning_table()
        assert "≤32" in table[0]["test_range"]
        assert table[0]["xdist_n"] > 0
        assert table[0]["cap"] > 0

    def test_last_row_has_nproc_note(self):
        table = _xdist_tuning_table()
        last = table[-1]
        assert "nproc" in last.get("note", "")
