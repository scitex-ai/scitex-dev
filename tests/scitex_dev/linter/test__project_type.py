"""Tests for ``scitex_dev.linter._project_type`` + the Pillar-3 severity
flip end-to-end (operator directive 12826).

When a project declares ``project-type: research`` in
``.scitex/dev/config.yaml``, the linter flips the ``io`` and ``path``
category severities from ``warning`` to ``error`` so a raw
``pd.read_parquet`` / bare ``open()`` BLOCKS the script-edit hook
(exit 2) rather than just warning the agent (exit 0).

Pin the flip end-to-end:
- ``parse_project_types_from_yaml`` handles scalar / inline-list /
  block-list YAML shapes (schema tolerance)
- ``detect_scitex_dev_project_types`` walks up filesystem looking for
  the config
- ``load_config`` populates ``LinterConfig.category_severity_override``
- ``checker._add`` honours the override (research → error, non-research
  → warning)
- per-rule override in ``per_rule_severity`` still wins (opt-out path)
"""

from __future__ import annotations

import pytest

from scitex_dev.linter._project_type import (
    detect_scitex_dev_project_types,
    parse_project_types_from_yaml,
)
from scitex_dev.linter._rules._base import Rule
from scitex_dev.linter.checker import SciTeXChecker
from scitex_dev.linter.config import LinterConfig, load_config


# Synthetic IO/PA/structure category rules used to drive the checker
# without depending on scitex-io being installed in the test env.
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


def _make_checker(config: LinterConfig | None = None) -> SciTeXChecker:
    """Build a SciTeXChecker against an empty source for direct ``_add`` calls."""
    return SciTeXChecker(source_lines=[""], filepath="<test>", config=config)


# ---------------------------------------------------------------------- #
# YAML parsing — schema tolerance                                        #
# ---------------------------------------------------------------------- #


class TestParseProjectTypesFromYaml:
    """Three admitted YAML shapes for ``project-type``."""

    def test_parses_scalar_form_into_singleton(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project-type: research\n")
        # Act
        types = parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset({"research"})

    def test_parses_inline_list_form_into_set(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project-type: [research, pip]\n")
        # Act
        types = parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset({"research", "pip"})

    def test_parses_block_list_form_into_set(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("project-type:\n  - research\n  - pip\n")
        # Act
        types = parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset({"research", "pip"})

    def test_returns_empty_set_when_key_missing(self, tmp_path):
        # Arrange
        cfg = tmp_path / "config.yaml"
        cfg.write_text("metadata:\n  cohorts: 3\n")
        # Act
        types = parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset()

    def test_returns_empty_set_when_file_unreadable(self, tmp_path):
        # Arrange — path that does not exist on disk.
        cfg = tmp_path / "does-not-exist.yaml"
        # Act
        types = parse_project_types_from_yaml(cfg)
        # Assert
        assert types == frozenset()


# ---------------------------------------------------------------------- #
# Walk-up filesystem detection                                           #
# ---------------------------------------------------------------------- #


class TestDetectScitexDevProjectTypes:
    """Walk-up loop mirroring ``_load_pyproject``."""

    def test_finds_config_two_levels_up_from_leaf(self, tmp_path):
        # Arrange — write the config two levels up, then probe from a leaf.
        (tmp_path / ".scitex" / "dev").mkdir(parents=True)
        (tmp_path / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type: research\n"
        )
        leaf = tmp_path / "src" / "pkg"
        leaf.mkdir(parents=True)
        # Act
        types = detect_scitex_dev_project_types(leaf)
        # Assert
        assert types == frozenset({"research"})

    def test_returns_empty_set_when_no_config_upstream(self, tmp_path):
        # Arrange — no .scitex/dev/config.yaml anywhere upward.
        leaf = tmp_path / "isolated"
        leaf.mkdir()
        # Act
        types = detect_scitex_dev_project_types(leaf)
        # Assert
        assert types == frozenset()


# ---------------------------------------------------------------------- #
# load_config populates category_severity_override on research repos     #
# ---------------------------------------------------------------------- #


class TestLoadConfigCategoryOverride:
    """``LinterConfig.category_severity_override`` is set on research repos."""

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

    def test_pip_only_project_leaves_override_empty(self, tmp_path):
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

    def test_hybrid_pip_plus_research_still_flips_categories(self, tmp_path):
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
    """``checker._add`` applies the category override under research mode."""

    def test_io_rule_severity_flipped_to_error_when_research_override_set(self):
        # Arrange — synthetic research-mode config; IO rule is warning by default.
        cfg = LinterConfig(category_severity_override={"io": "error"})
        checker = _make_checker(cfg)
        # Act
        checker._add(IO_RULE, line=10, col=0, source_line="pd.read_parquet(x)")
        # Assert — single combined check pins both issue count and flipped severity.
        emitted = [(i.rule.id, i.rule.severity) for i in checker.issues]
        assert emitted == [(IO_RULE.id, "error")], (
            f"research-mode override must flip io category warning→error; "
            f"got {emitted}"
        )

    def test_path_rule_severity_flipped_to_error_when_research_override_set(self):
        # Arrange
        cfg = LinterConfig(category_severity_override={"path": "error"})
        checker = _make_checker(cfg)
        # Act
        checker._add(PA_RULE, line=5, col=0, source_line="open('foo.txt')")
        # Assert
        emitted = [(i.rule.id, i.rule.severity) for i in checker.issues]
        assert emitted == [(PA_RULE.id, "error")], (
            f"research-mode override must flip path category warning→error; "
            f"got {emitted}"
        )

    def test_structure_rule_unaffected_by_io_path_only_override(self):
        # Arrange — research mode flips io+path; structure stays as-emitted.
        cfg = LinterConfig(
            category_severity_override={"io": "error", "path": "error"}
        )
        checker = _make_checker(cfg)
        # Act
        checker._add(STRUCTURE_RULE, line=1, col=0, source_line="def main():")
        # Assert
        emitted = [(i.rule.id, i.rule.severity) for i in checker.issues]
        assert emitted == [(STRUCTURE_RULE.id, "warning")], (
            f"structure rules must NOT flip when override targets io/path only; "
            f"got {emitted}"
        )

    def test_no_override_set_leaves_severity_unchanged_on_io_rule(self):
        # Arrange — non-research project, no override.
        cfg = LinterConfig()
        checker = _make_checker(cfg)
        # Act
        checker._add(IO_RULE, line=10, col=0, source_line="pd.read_parquet(x)")
        # Assert
        emitted = [(i.rule.id, i.rule.severity) for i in checker.issues]
        assert emitted == [(IO_RULE.id, "warning")], (
            f"no override → severity unchanged; got {emitted}"
        )

    def test_per_rule_severity_overrides_category_override_on_same_rule(self):
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
        emitted = [(i.rule.id, i.rule.severity) for i in checker.issues]
        assert emitted == [(IO_RULE.id, "warning")], (
            f"per_rule_severity must win over category_severity_override; "
            f"got {emitted}"
        )
