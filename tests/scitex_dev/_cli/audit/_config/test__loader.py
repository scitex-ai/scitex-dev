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


def test_load_falls_through_to_heuristic_when_no_config_cfg_project_types_frozenset_pip(
    tmp_path,
):
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


# metadata.app accessor (operator directive 2026-06-14) ----------------------


def _write_config_with_metadata(repo: Path, metadata_block: str) -> None:
    """Write a `.scitex/dev/config.yaml` with project-type + the given
    metadata: block. Caller supplies the block body indented to match
    the YAML schema."""
    cfg_path = repo / ".scitex/dev/config.yaml"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text("project-type:\n  - pip\nmetadata:\n" + metadata_block)


def test_app_metadata_returns_empty_when_no_config_app_metadata_dict(tmp_path):
    # Arrange — no config file at all.
    _seed_pip(tmp_path)

    # Act
    cfg = load_config(tmp_path)

    # Assert — heuristic path, no metadata.app block, accessor returns {}.
    assert cfg.app_metadata == {}


def test_app_metadata_returns_empty_when_metadata_lacks_app_key(tmp_path):
    # Arrange — metadata: present (cohorts), but no `app:` sub-block.
    _write_config_with_metadata(tmp_path, "  cohorts: 3\n")

    # Act
    cfg = load_config(tmp_path)

    # Assert
    assert cfg.metadata.get("cohorts") == 3
    assert cfg.app_metadata == {}


def test_app_metadata_round_trips_full_schema(tmp_path):
    # Arrange — declare the full operator-approved metadata.app schema.
    _write_config_with_metadata(
        tmp_path,
        "  app:\n"
        "    category: writer\n"
        '    official: "true"\n'
        '    pre_installed: "true"\n'
        '    is_hub_app: "true"\n'
        '    author: "Yusuke Watanabe"\n',
    )

    # Act
    cfg = load_config(tmp_path)

    # Assert — the canonical accessor returns the same dict the loader stored.
    app = cfg.app_metadata
    assert app["category"] == "writer"
    assert app["author"] == "Yusuke Watanabe"
    # `official` / `pre_installed` / `is_hub_app` arrive as the loader's parsed
    # form (PyYAML returns bool; minimal-YAML returns str). Both shapes are
    # acceptable here — consumers normalise; this test only asserts that the
    # key reached the accessor at all.
    assert "official" in app
    assert "pre_installed" in app
    assert "is_hub_app" in app


def test_app_metadata_returns_empty_when_app_key_is_not_a_dict(tmp_path):
    # Arrange — defensive case: `app:` typed as a scalar instead of mapping.
    _write_config_with_metadata(tmp_path, "  app: not-a-dict\n")

    # Act
    cfg = load_config(tmp_path)

    # Assert — accessor must NOT propagate a non-dict (would break consumers
    # that call `.get(...)` on the return value).
    assert cfg.app_metadata == {}


def test_app_metadata_preserves_unknown_keys(tmp_path):
    # Arrange — operator may experiment with extra keys before the schema
    # docs catch up; the accessor must not filter them out.
    _write_config_with_metadata(
        tmp_path,
        "  app:\n"
        "    category: writer\n"
        "    icon: writer.svg\n"
        "    route: /apps/writer/\n",
    )

    # Act
    cfg = load_config(tmp_path)

    # Assert
    app = cfg.app_metadata
    assert app["icon"] == "writer.svg"
    assert app["route"] == "/apps/writer/"


def test_app_metadata_works_under_override_source_app_metadata_dict(tmp_path):
    # Arrange — `override_types` short-circuits the YAML read entirely.
    # The accessor must still return {} (not raise) for the override path.

    # Act
    cfg = load_config(tmp_path, override_types=["pip"])

    # Assert
    assert cfg.source == "override"
    assert cfg.app_metadata == {}
