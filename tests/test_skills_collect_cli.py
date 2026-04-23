"""Regression tests for scitex-dev#6 — `skills collect` requires destination."""

from __future__ import annotations

import subprocess


class TestSkillsCollectCLI:
    def test_destination_is_required(self):
        """Issue #6: `collect` must fail with a clear error when no
        destination argument is given."""
        r = subprocess.run(
            ["scitex-dev", "skills", "collect"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode != 0
        combined = r.stdout + r.stderr
        # Click's usual error format
        assert "Missing argument" in combined
        assert "DESTINATION" in combined

    def test_help_mentions_destination(self):
        r = subprocess.run(
            ["scitex-dev", "skills", "collect", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0
        assert "DESTINATION" in r.stdout

    def test_dry_run_works_with_explicit_dest(self, tmp_path):
        dest = tmp_path / "skills-out"
        r = subprocess.run(
            ["scitex-dev", "skills", "collect", str(dest), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0
        # Should mention the dest path in the preview
        assert str(dest) in (r.stdout + r.stderr)


# EOF
