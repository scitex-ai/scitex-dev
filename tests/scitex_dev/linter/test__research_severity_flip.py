"""Tests for Pillar 3 — research-category severity flip (operator 12826).

When a project declares ``project-type: research`` in
``.scitex/dev/config.yaml``, the linter flips the ``io`` and ``path``
category severities from ``warning`` to ``error`` so a raw
``pd.read_parquet`` / bare ``open()`` BLOCKS the script-edit hook
(exit 2) rather than just warning the agent (exit 0).

Pin the flip end-to-end:
- ``load_config`` detects the YAML
- ``LinterConfig.category_severity_override`` is populated
- ``checker._add`` honours the override (research → error, non-research
  → warning)
- per-rule override in ``per_rule_severity`` still wins (opt-out path)
- block-list YAML form (``project-type:\\n  - research``) and inline
  scalar form (``project-type: research``) both detected
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from scitex_dev.linter.checker import Issue, SciTeXChecker
from scitex_dev.linter.config import (
    LinterConfig,
    _detect_scitex_dev_project_types,
    _parse_project_types_from_yaml,
    load_config,
)
from scitex_dev.linter._rules._base import Rule


# Synthetic IO/PA category rules used to drive the checker without
# depending on scitex-io being installed in the test env.
IO_RULE = Rule(
    id="STX-IO-TEST",
    severity="warning",
    category="io",
    message="synthetic io rule",
    suggestion="suggestion",
)
PA_RULE = Rule(
    id="STX-PA-TEST",
    severity="warning",
    category="path",
    message="synthetic path rule",
    suggestion="suggestion",
)
STRUCTURE_RULE = Rule(
    id="STX-S-TEST",
    severity="warning",
    category="structure",
    message="synthetic structure rule",
    suggestion="suggestion",
)


def _make_checker(
    config: LinterConfig | None = None,
) -> SciTeXChecker:
    """Build a SciTeXChecker against an empty source for direct ``_add`` calls."""
    return SciTeXChecker(source_lines=[""], filepath="<test>", config=config)


# ---------------------------------------------------------------------- #
# YAML parsing — schema tolerance                                         #
# ---------------------------------------------------------------------- #


class TestParseProjectTypesFromYaml:
    def test_scalar_form(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project-type: research\n")
        # Act
        types = _parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset({"research"})

    def test_inline_list_form(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project-type: [research, pip]\n")
        # Act
        types = _parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset({"research", "pip"})

    def test_block_list_form(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project-type:\n  - research\n  - pip\n")
        # Act
        types = _parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset({"research", "pip"})

    def test_missing_key_returns_empty(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("metadata:\n  cohorts: 3\n")
        # Act
        types = _parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset()


# ---------------------------------------------------------------------- #
# Walk-up detection                                                      #
# ---------------------------------------------------------------------- #


class TestDetectScitexDevProjectTypes:
    def test_finds_config_in_parent_directory(self, tmp_path):
        # Arrange — write the config two levels up, then probe from a leaf.
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: research\n"
        )
        leaf = tmp_path / "src" / "pkg"
        leaf.mkdir(parents=True)
        # Act
        types = _detect_scitex_dev_project_types(leaf)
        # Assert
        assert types == frozenset({"research"})

    def test_no_config_returns_empty(self, tmp_path):
        # Arrange — no .scitex/dev/config.yaml anywhere upward.
        leaf = tmp_path / "isolated"
        leaf.mkdir()
        # Act
        types = _detect_scitex_dev_project_types(leaf)
        # Assert
        assert types == frozenset()


# ---------------------------------------------------------------------- #
# load_config populates category_severity_override on research repos     #
# ---------------------------------------------------------------------- #


class TestLoadConfigCategoryOverride:
    def test_research_project_flips_io_and_path_to_error(self, tmp_path):
        # Arrange
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: research\n"
        )
        # Act
        cfg = load_config(start_path=str(tmp_path))
        # Assert
        assert cfg.category_severity_override == {
            "io": "error",
            "path": "error",
        }

    def test_non_research_project_leaves_override_empty(self, tmp_path):
        # Arrange — pip-only project, no research flip expected.
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: pip\n"
        )
        # Act
        cfg = load_config(start_path=str(tmp_path))
        # Assert
        assert cfg.category_severity_override == {}

    def test_no_scitex_dev_config_leaves_override_empty(self, tmp_path):
        # Arrange — no .scitex/dev/config.yaml at all.
        # Act
        cfg = load_config(start_path=str(tmp_path))
        # Assert
        assert cfg.category_severity_override == {}

    def test_hybrid_research_plus_pip_still_flips(self, tmp_path):
        # Arrange — both project-types listed (hybrid repo).
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type:\n  - pip\n  - research\n"
        )
        # Act
        cfg = load_config(start_path=str(tmp_path))
        # Assert
        assert cfg.category_severity_override == {
            "io": "error",
            "path": "error",
        }


# ---------------------------------------------------------------------- #
# Checker honours the override                                           #
# ---------------------------------------------------------------------- #


class TestCheckerHonoursCategoryOverride:
    def test_io_rule_severity_flipped_to_error_when_research(self):
        # Arrange — synthetic research-mode config; IO rule is warning by default.
        cfg = LinterConfig(category_severity_override={"io": "error"})
        checker = _make_checker(cfg)
        # Act
        checker._add(IO_RULE, line=10, col=0, source_line="pd.read_parquet(x)")
        # Assert
        assert len(checker.issues) == 1
        assert checker.issues[0].rule.severity == "error", (
            "research-mode override must flip io category warning→error"
        )

    def test_path_rule_severity_flipped_to_error_when_research(self):
        # Arrange
        cfg = LinterConfig(category_severity_override={"path": "error"})
        checker = _make_checker(cfg)
        # Act
        checker._add(PA_RULE, line=5, col=0, source_line="open('foo.txt')")
        # Assert
        assert checker.issues[0].rule.severity == "error"

    def test_structure_rule_unaffected_by_io_path_override(self):
        # Arrange — research mode flips io+path; structure stays as-emitted.
        cfg = LinterConfig(category_severity_override={"io": "error", "path": "error"})
        checker = _make_checker(cfg)
        # Act
        checker._add(STRUCTURE_RULE, line=1, col=0, source_line="def main():")
        # Assert
        assert checker.issues[0].rule.severity == "warning", (
            "structure rules must NOT flip when override targets io/path only"
        )

    def test_no_override_leaves_severity_unchanged(self):
        # Arrange — non-research project, no override.
        cfg = LinterConfig()
        checker = _make_checker(cfg)
        # Act
        checker._add(IO_RULE, line=10, col=0, source_line="pd.read_parquet(x)")
        # Assert
        assert checker.issues[0].rule.severity == "warning"

    def test_per_rule_severity_overrides_category_override(self):
        # Arrange — research mode flips io→error, but per-rule pins this
        # specific rule back to warning. Per-rule wins.
        cfg = LinterConfig(
            category_severity_override={"io": "error"},
            per_rule_severity={"STX-IO-TEST": "warning"},
        )
        checker = _make_checker(cfg)
        # Act
        checker._add(IO_RULE, line=10, col=0, source_line="pd.read_parquet(x)")
        # Assert
        assert checker.issues[0].rule.severity == "warning", (
            "per_rule_severity must win over category_severity_override"
        )
