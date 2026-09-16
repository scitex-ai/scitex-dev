"""Regression tests for scitex-dev#6 — `skills collect` requires destination."""

from __future__ import annotations

import subprocess

import click
from click.testing import CliRunner

from scitex_dev._cli.skills._manage._install_cmd import register


def test_install_writes_manifest_and_returns_projection_envelope(tmp_path):
    # Arrange
    @click.group()
    def skills():
        pass

    register(skills)
    destination = tmp_path / "skills"

    # Act
    result = CliRunner().invoke(
        skills,
        [
            "install",
            "--dest",
            str(destination),
            "--package",
            "scitex-dev",
            "--link",
            "--clean",
            "--json",
        ],
    )

    # Assert
    import json

    payload = json.loads(result.stdout)
    assert (
        result.exit_code,
        payload["schema_version"],
        payload["projection_sha256"].startswith("sha256:"),
        payload["manifest"],
        payload["findings"],
        (destination / ".scitex-skills.json").is_file(),
    ) == (
        0,
        "scitex-skills-projection/2",
        True,
        str(destination.resolve() / ".scitex-skills.json"),
        [],
        True,
    )


def test_install_fails_and_returns_findings_for_obsolete_projection(tmp_path):
    # Arrange
    @click.group()
    def skills():
        pass

    register(skills)
    destination = tmp_path / "skills"
    obsolete = destination / "obsolete" / "SKILL.md"
    obsolete.parent.mkdir(parents=True)
    obsolete.write_text("# obsolete\n", encoding="utf-8")

    # Act
    result = CliRunner().invoke(
        skills,
        [
            "install",
            "--dest",
            str(destination),
            "--package",
            "scitex-dev",
            "--link",
            "--clean",
            "--json",
        ],
    )

    # Assert
    import json

    payload = json.loads(result.stdout)
    assert (
        result.exit_code,
        payload["ok"],
        {(finding["code"], finding["kind"]) for finding in payload["findings"]},
    ) == (1, False, {("SP-301", "obsolete")})


def test_install_dry_run_uses_projection_envelope_without_writing(tmp_path):
    # Arrange
    @click.group()
    def skills():
        pass

    register(skills)
    destination = tmp_path / "skills"

    # Act
    result = CliRunner().invoke(
        skills,
        [
            "install",
            "--dest",
            str(destination),
            "--package",
            "scitex-dev",
            "--dry-run",
            "--json",
        ],
    )

    # Assert
    import json

    payload = json.loads(result.stdout)
    assert (
        result.exit_code,
        payload["schema_version"],
        payload["projection_sha256"],
        payload["findings"],
        payload["dry_run"],
        destination.exists(),
    ) == (0, "scitex-skills-projection/2", None, [], True, False)


class TestSkillsCollectCLI:
    def test_destination_is_required_r_returncode_0(self):
        """Issue #6: `collect` must fail with a clear error when no
        destination argument is given."""
        # Arrange
        # Act
        # Assert
        r = subprocess.run(
            ["scitex-dev", "skills", "collect"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode != 0
        combined = r.stdout + r.stderr
        # Click's usual error format


    def test_destination_is_required_missing_argument_in_combined(self):
        """Issue #6: `collect` must fail with a clear error when no
        destination argument is given."""
        # Arrange
        # Act
        # Assert
        r = subprocess.run(
            ["scitex-dev", "skills", "collect"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = r.stdout + r.stderr
        # Click's usual error format
        assert "Missing argument" in combined


    def test_destination_is_required_destination_in_combined(self):
        """Issue #6: `collect` must fail with a clear error when no
        destination argument is given."""
        # Arrange
        # Act
        # Assert
        r = subprocess.run(
            ["scitex-dev", "skills", "collect"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = r.stdout + r.stderr
        # Click's usual error format
        assert "DESTINATION" in combined

    def test_help_mentions_destination_r_returncode_0(self):
        # Arrange
        # Act
        # Assert
        r = subprocess.run(
            ["scitex-dev", "skills", "collect", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0


    def test_help_mentions_destination_destination_in_r_stdout(self):
        # Arrange
        # Act
        # Assert
        r = subprocess.run(
            ["scitex-dev", "skills", "collect", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert "DESTINATION" in r.stdout

    def test_dry_run_works_with_explicit_dest_r_returncode_0(self, tmp_path):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "skills-out"
        r = subprocess.run(
            ["scitex-dev", "skills", "collect", str(dest), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0
        # Should mention the dest path in the preview


    def test_dry_run_works_with_explicit_dest_str_dest_in_r_stdout_r_stderr(self, tmp_path):
        # Arrange
        # Act
        # Assert
        dest = tmp_path / "skills-out"
        r = subprocess.run(
            ["scitex-dev", "skills", "collect", str(dest), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Should mention the dest path in the preview
        assert str(dest) in (r.stdout + r.stderr)


# EOF
