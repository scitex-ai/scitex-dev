"""Regression tests for the README-structure auditor (PS-142 truncation).

PS-142 must not report a mandatory `## Architecture` section as MISSING
merely because it lives past a byte offset the checker used to truncate
at. The rule previously read the README as a 16 KiB head-slice, so a
package whose README grew past that budget (e.g. scitex-storage, 23 KB)
got a false "missing mandatory `## Architecture`" finding — a check
reporting ABSENCE from input it never saw.

Each test is AAA with a single logical assertion, on a real file under
tmp_path (no mocks — PA-306).
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._audit import Violation
from scitex_dev._cli.audit._project._check_readme_structure import (
    check_readme_structure,
)
from scitex_dev._cli.audit._project._readme_structure_shared import read_readme


# ~20 KiB of filler — larger than the 16 KiB head-slice the checker used
# to truncate at, so any section placed after it falls past the old boundary.
_FILLER = ("filler line to push later sections past the old cap\n") * 400


def _readme_with_architecture_past_boundary() -> str:
    """A valid README whose `## Architecture` sits past the old 16 KiB cap."""
    return (
        "# demo-pkg\n\n"
        "## Problem and Solution\n\n"
        "| Pain | Fix |\n|------|-----|\n| slow | fast |\n\n"
        "## Quick Start\n\n"
        "```python\nimport demo\n```\n\n"
        f"{_FILLER}\n"
        "## Installation\n\n"
        "pip install demo\n\n"
        "## Architecture\n\n"
        "```mermaid\nflowchart TD\n  A --> B\n```\n"
    )


def test_read_readme_returns_content_past_old_truncation_boundary(
    tmp_path: Path,
) -> None:
    # Arrange: a README with a sentinel far past the old 16 KiB slice.
    readme = tmp_path / "README.md"
    sentinel = "SENTINEL_PAST_BOUNDARY"
    # _FILLER alone (~20 KiB) already exceeds the old 16 KiB head-slice.
    readme.write_text("# t\n\n" + _FILLER + "\n" + sentinel + "\n")

    # Act: read the README through the audit reader.
    text = read_readme(readme)

    # Assert: the whole file is returned, sentinel included.
    assert sentinel in text


def test_ps142_silent_when_architecture_present_past_old_boundary(
    tmp_path: Path,
) -> None:
    # Arrange: a README whose mandatory `## Architecture` lives past 16 KiB.
    readme = tmp_path / "README.md"
    # The `## Architecture` header lands past the old 16 KiB head-slice.
    readme.write_text(_readme_with_architecture_past_boundary())

    # Act: run the README-structure auditor.
    out: list[Violation] = []
    check_readme_structure(tmp_path, Violation, out)

    # Assert: PS-142 does NOT fire — the section is seen, not truncated away.
    assert not [v for v in out if v.rule == "PS-142"]
