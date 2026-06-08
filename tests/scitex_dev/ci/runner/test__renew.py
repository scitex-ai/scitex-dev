"""Tests for ``scitex_dev.ci.runner._renew``."""

from __future__ import annotations

from scitex_dev.ci.runner._renew import _parse_slurm_time


class TestParseSlurmTime:
    """Test SLURM time string parsing to total minutes."""

    def test_hours_and_minutes(self):
        assert _parse_slurm_time("01:30:00") == 90

    def test_hours_minutes_seconds(self):
        assert _parse_slurm_time("02:15:30") == 135

    def test_only_minutes(self):
        assert _parse_slurm_time("15") == 15

    def test_single_digit_only_minutes(self):
        assert _parse_slurm_time("5") == 5

    def test_only_minutes_with_seconds(self):
        assert _parse_slurm_time("45:00") == 45

    def test_zero(self):
        assert _parse_slurm_time("00:00:00") == 0

    def test_multi_day(self):
        assert _parse_slurm_time("1-00:00:00") == 1440

    def test_multi_day_with_hours(self):
        assert _parse_slurm_time("2-12:00:00") == 3600

    def test_single_digit_hours(self):
        assert _parse_slurm_time("0-05:00:00") == 300

    def test_strips_whitespace(self):
        assert _parse_slurm_time("  01:30:00  ") == 90

    def test_invalid_format_returns_zero(self):
        assert _parse_slurm_time("abc") == 0

    def test_empty_string_returns_zero(self):
        assert _parse_slurm_time("") == 0
