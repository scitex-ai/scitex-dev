"""Tests for `.scitex/dev/config.yaml` loader + heuristic."""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._config import (
    PROJECT_TYPES,
    detect_project_types,
    load_config,
    write_config,
)


def _seed_pip(repo: Path) -> None:
    (repo / "pyproject.toml").write_text('[project]\nname = "demo"\n')
    (repo / "src" / "demo").mkdir(parents=True)


def _seed_research(repo: Path) -> None:
    (repo / "scripts").mkdir()
    (repo / "data").mkdir()
    (repo / "config").mkdir()


# Heuristic ------------------------------------------------------------------


def test_heuristic_empty_repo_defaults_to_pip(tmp_path):
    # Arrange
    # Act
    # Assert
    assert detect_project_types(tmp_path) == frozenset({"pip"})


def test_heuristic_pip_only(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    assert detect_project_types(tmp_path) == frozenset({"pip"})


def test_heuristic_research_only(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_research(tmp_path)
    # No pyproject.toml + no src/ ⇒ heuristic returns research only.
    assert detect_project_types(tmp_path) == frozenset({"research"})


def test_heuristic_detects_hybrid_pip_and_research(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    _seed_research(tmp_path)
    assert detect_project_types(tmp_path) == frozenset({"pip", "research"})


# Load + applies -------------------------------------------------------------


def test_load_falls_through_to_heuristic_when_no_config_cfg_source_heuristic(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.source == "heuristic"


def test_load_falls_through_to_heuristic_when_no_config_cfg_project_types_frozenset_pip(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.project_types == frozenset({"pip"})


def test_load_reads_committed_config_cfg_source_config(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path)
    assert cfg.source == "config"


def test_load_reads_committed_config_cfg_project_types_frozenset_research(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path)
    assert cfg.project_types == frozenset({"research"})


def test_load_override_wins_over_config_cfg_source_override(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path, override_types=["pip"])
    assert cfg.source == "override"


def test_load_override_wins_over_config_cfg_project_types_frozenset_pip(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path, override_types=["pip"])
    assert cfg.project_types == frozenset({"pip"})


def test_applies_routes_ps_to_pip_cfg_applies_ps_133(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    cfg = load_config(tmp_path)
    assert cfg.applies("PS-133")


def test_applies_routes_ps_to_pip_not_cfg_applies_rp100(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    cfg = load_config(tmp_path)
    assert not cfg.applies("RP100")


def test_applies_routes_rp_to_research_cfg_applies_rp100(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path)
    assert cfg.applies("RP100")


def test_applies_routes_rp_to_research_not_cfg_applies_ps_133(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["research"])
    cfg = load_config(tmp_path)
    assert not cfg.applies("PS-133")


def test_applies_hybrid_runs_both_cfg_applies_ps_133(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["pip", "research"])
    cfg = load_config(tmp_path)
    assert cfg.applies("PS-133")


def test_applies_hybrid_runs_both_cfg_applies_rp100(tmp_path):
    # Arrange
    # Act
    # Assert
    _seed_pip(tmp_path)
    write_config(tmp_path, project_types=["pip", "research"])
    cfg = load_config(tmp_path)
    assert cfg.applies("RP100")


# Write ----------------------------------------------------------------------


def test_write_refuses_existing_without_overwrite(tmp_path):
    # Arrange
    # Act
    # Assert
    write_config(tmp_path, project_types=["pip"])
    with pytest.raises(FileExistsError):
        write_config(tmp_path, project_types=["pip"])


def test_write_overwrite_replaces_research_in_p_read_text(tmp_path):
    # Arrange
    # Act
    # Assert
    write_config(tmp_path, project_types=["pip"])
    p = write_config(tmp_path, project_types=["research"], overwrite=True)
    assert "research" in p.read_text()


def test_write_overwrite_replaces_pip_not_in_p_read_text(tmp_path):
    # Arrange
    # Act
    # Assert
    write_config(tmp_path, project_types=["pip"])
    p = write_config(tmp_path, project_types=["research"], overwrite=True)
    assert "- pip" not in p.read_text()


def test_project_types_constant():
    # Arrange
    # Act
    # Assert
    assert PROJECT_TYPES == frozenset(
        {"pip", "research", "special", "django", "deferred"}
    )


# Skip + whitelist (not yet wired into auditor; just round-trip the parse) ----


def test_skip_list_round_trips(tmp_path):
    # Arrange
    # Act
    # Assert
    cfg_path = tmp_path / ".scitex/dev/config.yaml"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(
        "project-type:\n  - pip\naudit:\n  skip:\n    - PS-108\n    - PS-127\n"
    )
    cfg = load_config(tmp_path)
    assert cfg.skip == frozenset({"PS-108", "PS-127"})
