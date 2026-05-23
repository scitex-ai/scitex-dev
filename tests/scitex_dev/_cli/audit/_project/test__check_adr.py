"""Tests for PS-173 — Architecture Decision Record (ADR) format.

ADRs are recommended-not-mandated: a repo with no `docs/adr/` gets no
finding. Once `docs/adr/` exists, the FORMAT is enforced — filename
`NNNN-<kebab-slug>.md` plus the lean five-section template (title +
Status / Context / Decision / Consequences), tolerant of the proven
scitex-agent-container exemplar shapes (`**Status:**` bold-line,
`## Problem` ≡ Context, `## Decisions` ≡ Decision).

No mocks (NM001-003) — real temp dirs + `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._config import load_config, write_config
from scitex_dev._cli.audit._project._check_adr import check_ps173_adr_format

_CONFORMING = (
    "# ADR: First decision (2026-05-23)\n\n"
    "## Status\nAccepted.\n\n"
    "## Context\nWhy this came up.\n\n"
    "## Decision\nWhat we chose.\n\n"
    "## Consequences\nWhat follows.\n"
)


def _findings(repo: Path) -> list:
    out: list = []
    check_ps173_adr_format(repo, out)
    return out


def _details(repo: Path) -> list[str]:
    return [v.detail for v in _findings(repo)]


def _write_adr(repo: Path, name: str, body: str) -> Path:
    adr_dir = repo / "docs" / "adr"
    adr_dir.mkdir(parents=True, exist_ok=True)
    p = adr_dir / name
    p.write_text(body)
    return p


# Presence is recommended, not mandated -------------------------------------


def test_no_docs_adr_dir_is_noop(tmp_path):
    # Arrange
    # Act
    out = _findings(tmp_path)
    # Assert
    assert out == []


def test_empty_docs_adr_dir_is_clean(tmp_path):
    # Arrange
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    # Act
    out = _findings(tmp_path)
    # Assert
    assert out == []


# Conforming ADR ------------------------------------------------------------


def test_conforming_adr_passes(tmp_path):
    # Arrange
    _write_adr(tmp_path, "0001-first-decision.md", _CONFORMING)
    # Act
    out = _findings(tmp_path)
    # Assert
    assert out == []


def test_bold_status_problem_decisions_synonyms_pass(tmp_path):
    # Arrange — the proven scitex-agent-container exemplar shape.
    body = (
        "# ADR: Some decision (2026-05-23)\n\n"
        "**Status:** Accepted.\n\n"
        "## Problem\nThe context, named Problem.\n\n"
        "## Decisions\nWhat we chose (plural heading).\n\n"
        "## Consequences\nWhat follows.\n"
    )
    _write_adr(tmp_path, "0002-some-decision.md", body)
    # Act
    out = _findings(tmp_path)
    # Assert
    assert out == []


# Filename format -----------------------------------------------------------


def test_missing_numeric_prefix_flags_filename(tmp_path):
    # Arrange
    _write_adr(tmp_path, "first-decision.md", _CONFORMING)
    # Act
    details = _details(tmp_path)
    # Assert
    assert any("filename must be" in d for d in details)


def test_three_digit_prefix_flags_filename(tmp_path):
    # Arrange — 3 digits, not 4.
    _write_adr(tmp_path, "001-first.md", _CONFORMING)
    # Act
    details = _details(tmp_path)
    # Assert
    assert any("filename must be" in d for d in details)


def test_upper_case_slug_flags_filename(tmp_path):
    # Arrange — slug must be lowercase kebab.
    _write_adr(tmp_path, "0001-First-Decision.md", _CONFORMING)
    # Act
    details = _details(tmp_path)
    # Assert
    assert any("filename must be" in d for d in details)


def test_well_formed_filename_no_filename_finding(tmp_path):
    # Arrange
    _write_adr(tmp_path, "0042-a-longer-kebab-slug.md", _CONFORMING)
    # Act
    details = _details(tmp_path)
    # Assert
    assert not any("filename must be" in d for d in details)


# Required sections ---------------------------------------------------------


def test_missing_consequences_section_flagged(tmp_path):
    # Arrange
    body = "# T\n## Status\nx\n## Context\nx\n## Decision\nx\n"
    _write_adr(tmp_path, "0001-x.md", body)
    # Act
    details = _details(tmp_path)
    # Assert
    assert any("Consequences" in d for d in details)


def test_missing_status_section_flagged(tmp_path):
    # Arrange
    body = "# T\n## Context\nx\n## Decision\nx\n## Consequences\nx\n"
    _write_adr(tmp_path, "0001-x.md", body)
    # Act
    details = _details(tmp_path)
    # Assert
    assert any("missing required section" in d and "Status" in d for d in details)


def test_missing_title_flagged(tmp_path):
    # Arrange — no H1 title, only sections.
    body = "## Status\nx\n## Context\nx\n## Decision\nx\n## Consequences\nx\n"
    _write_adr(tmp_path, "0001-x.md", body)
    # Act
    details = _details(tmp_path)
    # Assert
    assert any("missing a title" in d for d in details)


# Cross-cutting routing (applies to all project kinds) ----------------------


def test_ps173_applies_to_pip_projects(tmp_path):
    # Arrange
    write_config(tmp_path, project_types=["pip"])
    cfg = load_config(tmp_path)
    # Act
    result = cfg.applies("PS-173")
    # Assert
    assert result is True


def test_ps173_applies_to_research_projects(tmp_path):
    # Arrange
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path)
    # Act
    result = cfg.applies("PS-173")
    # Assert
    assert result is True


def test_other_ps_rules_still_pip_only(tmp_path):
    # Arrange — PS-173's escape must not leak to sibling PS rules.
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path)
    # Act
    result = cfg.applies("PS-133")
    # Assert
    assert result is False
