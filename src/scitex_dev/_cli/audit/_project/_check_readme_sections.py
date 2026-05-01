"""README convention checks — PS107 / PS109 / PS110 / PS111 / PS112.

Codifies the SciTeX README template (see
``_skills/general/04_docs_01_readme.md`` and the literal template at
``_skills/general/04_docs_01_readme_template.md``). Detection mirrors
PS106 (``_check_readme_badges.py``): cheap substring/regex scans on the
first ~16 KB of README.md, warn-only.

False-positive guards:
- Skip every check when README is missing (PS101 covers that) or
  shorter than ``_MIN_README_BYTES`` (placeholder/scaffold READMEs).
- PS109/PS110/PS112 only scan the first 4 KB / 16 KB respectively, so
  late-document boilerplate doesn't get mis-detected as compliant.

Section names match the most common pattern across 8 surveyed READMEs
(scitex-python, scitex-io, scitex-stats, scitex-dev, figrecipe,
scitex-writer, scitex-scholar, scitex-git). See ``/tmp/readme_survey.md``
for the underlying analysis.
"""

from __future__ import annotations

import re
from pathlib import Path


_MIN_README_BYTES = 200
_HEAD_BYTES_BADGES = 4096
_HEAD_BYTES_SECTIONS = 16384


# PS107 — required H2 sections.
# Acceptable variants for "Quick Start" — both `## Quick Start` and
# `## Quickstart` are common in the wild.
_RE_INSTALLATION = re.compile(r"^##\s+Installation\b", re.MULTILINE | re.IGNORECASE)
_RE_QUICKSTART = re.compile(
    r"^##\s+(Quick\s*Start|Quickstart)\b", re.MULTILINE | re.IGNORECASE
)
_RE_PART_OF_SCITEX = re.compile(
    r"^##\s+Part\s+of\s+SciTeX\b", re.MULTILINE | re.IGNORECASE
)


# PS109 — PyPI version badge. Accepts badge.fury.io OR shields.io/pypi.
_RE_PYPI_BADGE = re.compile(
    r"(badge\.fury\.io/py/|img\.shields\.io/pypi/v/)", re.IGNORECASE
)


# PS110 — Four Freedoms blockquote. Tolerates the leading `>` with or
# without a space, and either `Four Freedoms for Research` or just
# `Four Freedoms` (most use the full phrase but stay forgiving).
_RE_FOUR_FREEDOMS = re.compile(
    r">\s*Four\s+Freedoms(?:\s+for\s+Research)?", re.IGNORECASE
)


# PS111 — banned personal email. The convention says READMEs should
# point at the community project, not a single maintainer's address.
_BANNED_EMAIL = "ywatanabe@scitex.ai"


# PS112 — SciTeX logo at top. Accepted forms (any one is enough):
#   - <img src=".../scitex-logo*.png" ...>
#   - <img src=".../scitex-logo-*.png" ...>
# inside the first 4 KB. We're permissive on path so both
# docs/assets/images/scitex-logo-*.png and docs/scitex-logo-*.png
# variants pass — both occur in the surveyed READMEs.
_RE_SCITEX_LOGO = re.compile(
    r"<img[^>]+src=[\"'][^\"']*scitex-logo[^\"']*\.(?:png|svg|jpg|jpeg)[\"']",
    re.IGNORECASE,
)


def _read_head(readme: Path, n: int) -> str | None:
    """Return the first `n` bytes of `readme` as text, or None on error/missing."""
    if not readme.is_file():
        return None
    try:
        text = readme.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return text[:n]


def _readme_is_substantive(readme: Path) -> bool:
    """True iff README exists and is at least ``_MIN_README_BYTES`` bytes."""
    if not readme.is_file():
        return False
    try:
        return readme.stat().st_size >= _MIN_README_BYTES
    except OSError:
        return False


def check_readme_sections(repo: Path, violation_cls: type, out: list) -> None:
    """Append PS107 / PS109 / PS110 / PS111 / PS112 violations.

    Each rule is independent; a missing README short-circuits all five
    (PS101 already flags missing pyproject and a future check could flag
    missing README — we don't double-flag here).
    """
    readme = repo / "README.md"
    if not _readme_is_substantive(readme):
        return

    head_sections = _read_head(readme, _HEAD_BYTES_SECTIONS)
    head_badges = _read_head(readme, _HEAD_BYTES_BADGES)
    if head_sections is None or head_badges is None:
        return

    # PS107 — required sections
    missing: list[str] = []
    if not _RE_INSTALLATION.search(head_sections):
        missing.append("## Installation")
    if not _RE_QUICKSTART.search(head_sections):
        missing.append("## Quick Start")
    if not _RE_PART_OF_SCITEX.search(head_sections):
        missing.append("## Part of SciTeX")
    if missing:
        out.append(
            violation_cls(
                "PS107",
                str(readme),
                (
                    "README.md is missing required H2 section(s): "
                    + ", ".join(missing)
                    + ". See _skills/general/04_docs_01_readme_template.md "
                    "for the canonical layout."
                ),
            )
        )

    # PS109 — PyPI version badge
    if not _RE_PYPI_BADGE.search(head_badges):
        out.append(
            violation_cls(
                "PS109",
                str(readme),
                (
                    "README.md is missing a PyPI version badge in the first ~4 KB. "
                    "Add a `[![PyPI](https://badge.fury.io/py/<pkg>.svg)]"
                    "(https://pypi.org/project/<pkg>/)` or "
                    "`[![PyPI](https://img.shields.io/pypi/v/<pkg>.svg)](...)` line "
                    "near the title."
                ),
            )
        )

    # PS110 — Four Freedoms footer (search the whole readable text for the
    # blockquote line — it lives near the bottom of the file).
    full = readme.read_text(encoding="utf-8", errors="replace")
    if not _RE_FOUR_FREEDOMS.search(full):
        out.append(
            violation_cls(
                "PS110",
                str(readme),
                (
                    "README.md does not contain the Four Freedoms for Research "
                    "blockquote. Append the canonical block under "
                    "`## Part of SciTeX` (see _skills/general/"
                    "04_docs_01_readme_template.md)."
                ),
            )
        )

    # PS111 — banned personal email
    if _BANNED_EMAIL in full:
        out.append(
            violation_cls(
                "PS111",
                str(readme),
                (
                    f"README.md contains the banned personal email "
                    f"`{_BANNED_EMAIL}`. SciTeX is a community project; "
                    "remove the address (use the project URL or GitHub "
                    "issues for contact)."
                ),
            )
        )

    # PS112 — SciTeX logo at top
    if not _RE_SCITEX_LOGO.search(head_badges):
        out.append(
            violation_cls(
                "PS112",
                str(readme),
                (
                    "README.md is missing a SciTeX logo image in the first ~4 KB. "
                    'Add a centered `<img src="docs/scitex-logo-blue-cropped.png" '
                    "...>` (or `docs/assets/images/scitex-logo-blue-cropped.png`) "
                    "near the title."
                ),
            )
        )
