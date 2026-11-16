#!/usr/bin/env python3
"""The general scitexification skills must stay project-agnostic.

``_skills/scientific/06_scitexification/`` and the ``04_clew_*`` chapters
teach ANY agent how to translate a real-world research project into the
SciTeX way. They must not name particular benchmarks, benchmark artefacts,
one consumer project, or internal chat/operator threads — that material
belongs in the consuming project's own repo. They must also teach the
current ``@stx.session`` API, not the deprecated spellings.

These tests scan the real shipped markdown files (no fixtures, no mocks).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Scan the checkout under test, not whichever copy happens to be installed.
REPO_ROOT = Path(__file__).resolve().parents[2]
SCIENTIFIC = REPO_ROOT / "src" / "scitex_dev" / "_skills" / "scientific"

# Files that make up the general scitexification teaching surface.
GENERAL_SKILL_FILES = sorted(
    [
        *(SCIENTIFIC / "06_scitexification").rglob("*.md"),
        *SCIENTIFIC.glob("04_clew_*.md"),
        SCIENTIFIC / "05_private-skills_01_consumer-project.md",
    ]
)

FORBIDDEN = {
    # Benchmarks / benchmark artefacts (development material of one paper).
    "benchmark name": re.compile(
        r"core-?bench|bix-?bench|bio-?mystery|futurehouse|codeocean|code ocean",
        re.IGNORECASE,
    ),
    "benchmark artefact": re.compile(r"capsule", re.IGNORECASE),
    # One specific consumer project.
    "consumer project": re.compile(r"paper-scitex-clew", re.IGNORECASE),
    # Internal chats / operator messages.
    "internal chat": re.compile(
        r"telegram|\bmsg\s*#?\d+|A2A thread|operator decision", re.IGNORECASE
    ),
    # Deprecated session API spellings taught as usage.
    "deprecated stx.INJECTED": re.compile(r"=\s*stx\.INJECTED\b"),
    "@stx.session.start as decorator": re.compile(r"@stx\.session\.start\b(?!`)"),
}

MD_LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)")


def test_general_skill_scope_is_non_empty():
    # Arrange
    names = {p.name for p in GENERAL_SKILL_FILES}
    # Act
    has_playbook = "00_playbook.md" in names
    # Assert
    assert has_playbook and len(GENERAL_SKILL_FILES) >= 15, names


@pytest.mark.parametrize(
    ("label", "sample"),
    [
        ("benchmark name", "see the CORE-Bench cohort"),
        ("benchmark artefact", "capsule-1624349"),
        ("consumer project", "proj-paper-scitex-clew"),
        ("internal chat", "Per operator decision (Telegram msg 125)."),
        ("deprecated stx.INJECTED", "def main(CONFIG=stx.INJECTED):"),
        ("@stx.session.start as decorator", "@stx.session.start\ndef main():"),
    ],
)
def test_forbidden_patterns_catch_known_offenders(label, sample):
    # Arrange
    pattern = FORBIDDEN[label]
    # Act
    hit = pattern.search(sample)
    # Assert
    assert hit is not None


@pytest.mark.parametrize(
    "path", GENERAL_SKILL_FILES, ids=lambda p: str(p.relative_to(SCIENTIFIC))
)
def test_general_skill_has_no_project_specific_tokens(path):
    # Arrange
    lines = path.read_text(encoding="utf-8").splitlines()
    # Act
    hits = [
        f"{path.name}:{i}: [{label}] {line.strip()}"
        for i, line in enumerate(lines, 1)
        for label, pattern in FORBIDDEN.items()
        if pattern.search(line)
    ]
    # Assert
    assert hits == [], "\n".join(hits)


@pytest.mark.parametrize(
    "path", GENERAL_SKILL_FILES, ids=lambda p: str(p.relative_to(SCIENTIFIC))
)
def test_general_skill_relative_md_links_resolve(path):
    # Arrange
    targets = MD_LINK.findall(path.read_text(encoding="utf-8"))
    # Act
    dead = [t for t in targets if not (path.parent / t).resolve().is_file()]
    # Assert
    assert dead == [], f"{path.name}: dead links {dead}"
