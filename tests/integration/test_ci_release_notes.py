"""Run the actual release-note step against owned changelog sections."""

import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/pypi-publish-and-github-release-on-tag.yml"


@pytest.fixture
def release_notes_step():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    return next(
        step["run"]
        for step in workflow["jobs"]["release"]["steps"]
        if step.get("name") == "Extract release notes from CHANGELOG.md"
    )


@pytest.mark.parametrize(
    "changelog, expected",
    [
        (
            "## [Unreleased]\n- Pending.\n\n"
            "## [0.62.29] - 2026-11-12\n- Preserve hooks.\n\n"
            "## [0.62.28] - 2026-11-12\n- Older.\n",
            "- Preserve hooks.",
        ),
        (
            "## [0X62Y29] - 2026-11-12\n- Wrong dotted match.\n\n"
            "## [0.62.29] - 2026-11-12\n- Exact release.\n\n"
            "## [0.62.290] - 2026-11-12\n- Wrong prefix.\n",
            "- Exact release.",
        ),
        (
            "## [0.62.290] - 2026-11-12\n- Longer version.\n\n"
            "## [0.62.29] - 2026-11-12\n- Requested version.\n",
            "- Requested version.",
        ),
        (
            "## [Unreleased]\n- Pending.\n",
            "Release v0.62.29. See CHANGELOG.md for details.",
        ),
    ],
)
def test_release_notes_selects_literal_heading(
    tmp_path, release_notes_step, changelog, expected
):
    # Arrange
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    environment = {"PATH": os.defpath, "RELEASE_TAG": "v0.62.29"}

    # Act
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", release_notes_step],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
    )

    # Assert
    observed = {
        "returncode": result.returncode,
        "stderr": result.stderr,
        "notes": (tmp_path / "release-notes.md").read_text().strip(),
    }
    assert observed == {"returncode": 0, "stderr": "", "notes": expected}
