"""Tests for `.scitex/dev/config.yaml` loader + heuristic."""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._config import (
    CAPABILITY_RULES,
    KNOWN_CAPABILITIES,
    PROJECT_TYPES,
    capability_for_rule,
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


def test_app_metadata_returns_empty_when_metadata_lacks_app_key_app_metadata_is_dict(
    tmp_path,
):
    # Arrange — metadata: present (cohorts), but no `app:` sub-block.
    _write_config_with_metadata(tmp_path, "  cohorts: 3\n")
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.app_metadata == {}


def test_app_metadata_returns_empty_when_metadata_lacks_app_key_cohorts_preserved(
    tmp_path,
):
    # Arrange — sibling sub-block (cohorts) must still round-trip; this
    # guards against the accessor inadvertently wiping unrelated keys.
    _write_config_with_metadata(tmp_path, "  cohorts: 3\n")
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.metadata.get("cohorts") == 3


def _full_schema_app_block() -> str:
    return (
        "  app:\n"
        "    category: writer\n"
        '    official: "true"\n'
        '    pre_installed: "true"\n'
        '    is_hub_app: "true"\n'
        '    author: "Yusuke Watanabe"\n'
    )


def test_app_metadata_round_trips_category(tmp_path):
    # Arrange
    _write_config_with_metadata(tmp_path, _full_schema_app_block())
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.app_metadata["category"] == "writer"


def test_app_metadata_round_trips_author(tmp_path):
    # Arrange
    _write_config_with_metadata(tmp_path, _full_schema_app_block())
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.app_metadata["author"] == "Yusuke Watanabe"


@pytest.mark.parametrize("key", ["official", "pre_installed", "is_hub_app"])
def test_app_metadata_round_trips_bool_keys_present_in_accessor(tmp_path, key):
    # Arrange — bool values arrive as PyYAML bool (True) OR minimal-YAML
    # str ("true") depending on which parser is active in CI. Both shapes
    # are acceptable; the test only asserts the KEY reached the accessor.
    _write_config_with_metadata(tmp_path, _full_schema_app_block())
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert key in cfg.app_metadata


def test_app_metadata_returns_empty_when_app_key_is_not_a_dict(tmp_path):
    # Arrange — defensive case: `app:` typed as a scalar instead of mapping.
    _write_config_with_metadata(tmp_path, "  app: not-a-dict\n")
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.app_metadata == {}


def test_app_metadata_preserves_unknown_key_icon(tmp_path):
    # Arrange — operator may experiment with extra keys before the schema
    # docs catch up; the accessor must not filter them out.
    _write_config_with_metadata(
        tmp_path,
        "  app:\n    category: writer\n    icon: writer.svg\n    route: /apps/writer/\n",
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.app_metadata["icon"] == "writer.svg"


def test_app_metadata_preserves_unknown_key_route(tmp_path):
    # Arrange
    _write_config_with_metadata(
        tmp_path,
        "  app:\n    category: writer\n    icon: writer.svg\n    route: /apps/writer/\n",
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.app_metadata["route"] == "/apps/writer/"


def test_app_metadata_under_override_source_returns_empty(tmp_path):
    # Arrange — `override_types` short-circuits the YAML read entirely;
    # the accessor must still return {} (not raise) for the override path.
    # Act
    cfg = load_config(tmp_path, override_types=["pip"])
    # Assert
    assert cfg.app_metadata == {}


def test_app_metadata_under_override_source_marks_source_override(tmp_path):
    # Arrange — sister test guarding the override marker stays correct.
    # Act
    cfg = load_config(tmp_path, override_types=["pip"])
    # Assert
    assert cfg.source == "override"


# ---------------------------------------------------------------------------
# CAPABILITY knob — the leaf-side package-type knob's fixed contract.
# (Split out of the former test__capability_knob.py orphan; the symbols under
# test all live in this module's mirror src, _config/_loader.py.)
#
# A leaf declares ``audit.capabilities: [no-mcp, no-umbrella]`` in its
# ``.scitex/dev/config.yaml``; the auditor reads it and SKIPS the matching rule
# with a VISIBLE notice. Each capability gates a FIXED set of rule codes, so it
# can never silence an unrelated rule. Operator directive 2026-06-22.
# ---------------------------------------------------------------------------


def _write_caps_config(repo: Path, capabilities: list[str] | None) -> None:
    """Write a `.scitex/dev/config.yaml` for `repo`, optionally with caps."""
    cfg_dir = repo / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    body = "project-type:\n  - pip\n"
    if capabilities is not None:
        body += "audit:\n  capabilities:\n"
        for cap in capabilities:
            body += f"    - {cap}\n"
    (cfg_dir / "config.yaml").write_text(body, encoding="utf-8")


def test_known_capabilities_are_no_mcp_and_no_umbrella():
    # Arrange
    expected = frozenset({"no-mcp", "no-umbrella"})
    # Act
    actual = KNOWN_CAPABILITIES
    # Assert
    assert actual == expected


def test_no_mcp_gates_section6_rule():
    # Arrange
    # Act
    gated = CAPABILITY_RULES["no-mcp"]
    # Assert
    assert gated == frozenset({"§6"})


def test_no_umbrella_gates_ps501_and_ps503():
    # Arrange
    # Act
    gated = CAPABILITY_RULES["no-umbrella"]
    # Assert
    assert gated == frozenset({"PS-501", "PS-503"})


def test_capability_for_section6_is_no_mcp():
    # Arrange
    # Act
    cap = capability_for_rule("§6")
    # Assert
    assert cap == "no-mcp"


def test_capability_for_ps501_is_no_umbrella():
    # Arrange
    # Act
    cap = capability_for_rule("PS-501")
    # Assert
    assert cap == "no-umbrella"


def test_capability_for_ungated_rule_is_none():
    # Arrange
    # Act
    cap = capability_for_rule("PS-101")
    # Assert
    assert cap is None


def test_load_config_keeps_known_capabilities(tmp_path):
    # Arrange
    _write_caps_config(tmp_path, ["no-mcp", "no-umbrella", "totally-bogus"])
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.capabilities == frozenset({"no-mcp", "no-umbrella"})


def test_load_config_drops_unknown_capability(tmp_path):
    # Arrange
    _write_caps_config(tmp_path, ["no-mcp", "totally-bogus"])
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.has_capability("totally-bogus") is False


def test_load_config_has_no_capabilities_when_absent(tmp_path):
    # Arrange
    _write_caps_config(tmp_path, capabilities=None)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.capabilities == frozenset()


# ---------------------------------------------------------------------------
# `audit.exemptions` END-TO-END — from the YAML a repo owner actually writes.
#
# The shape-level cases live in `test__exemptions.py`; these three go through
# a REAL `.scitex/dev/config.yaml` so the whole path (YAML -> loader ->
# ProjectConfig) is exercised, including the POSITIVE CONTROL that the correct
# spelling still exempts. Field defect, scitex-hub 2026-07-29.
# ---------------------------------------------------------------------------

#: hub's spelling: a LIST of entries instead of a mapping keyed by rule code.
_HUB_LIST_FORM_YAML = (
    "project-type:\n  - pip\n"
    "audit:\n"
    "  exemptions:\n"
    "    - rule: PS-224\n"
    "      path: .github/workflows/e2e-mobile.yml::playwright-mobile\n"
    "      reason: 'mobile browsers ship only on the hosted image'\n"
)

#: The spelling the parser wants.
_GOOD_MAPPING_YAML = (
    "project-type:\n  - pip\n"
    "audit:\n"
    "  exemptions:\n"
    "    PS-224:\n"
    "      - path: .github/workflows/e2e-mobile.yml::playwright-mobile\n"
    "        line: 0\n"
    "        reason: 'mobile browsers ship only on the hosted image'\n"
)


def _write_raw_config(repo: Path, body: str) -> Path:
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(body, encoding="utf-8")
    return cfg


def test_list_form_exemptions_block_records_an_error(tmp_path):
    # Arrange — this config used to load as "no exemptions, no problems".
    _write_raw_config(tmp_path, _HUB_LIST_FORM_YAML)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert len(cfg.exemption_errors) == 1


def test_list_form_exemptions_error_names_the_received_type(tmp_path):
    # Arrange
    _write_raw_config(tmp_path, _HUB_LIST_FORM_YAML)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert "got a list" in cfg.exemption_errors[0]


def test_list_form_exemptions_block_exempts_nothing(tmp_path):
    # Arrange
    _write_raw_config(tmp_path, _HUB_LIST_FORM_YAML)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.exemptions == ()


def test_mapping_form_exemptions_block_still_parses(tmp_path):
    # Arrange — POSITIVE CONTROL: a suite asserting only the new errors would
    # pass on a loader that rejected every shape.
    _write_raw_config(tmp_path, _GOOD_MAPPING_YAML)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert len(cfg.exemptions) == 1


def test_mapping_form_exemptions_block_reports_no_errors(tmp_path):
    # Arrange
    _write_raw_config(tmp_path, _GOOD_MAPPING_YAML)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.exemption_errors == ()


def test_mapping_form_exemption_matches_its_site(tmp_path):
    # Arrange — POSITIVE CONTROL, at the level that matters: the exemption
    # must still SUPPRESS its site, not merely parse.
    _write_raw_config(tmp_path, _GOOD_MAPPING_YAML)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert (
        cfg.exemption_for(
            "PS-224", ".github/workflows/e2e-mobile.yml::playwright-mobile", 0
        )
        is not None
    )


def test_load_config_honours_audit_block_without_project_type(tmp_path):
    # Arrange - a config that declares ONLY an audit block (no project-type),
    # like an alias package's capability knob. The audit block must still
    # apply (types fall back to heuristic detection).
    cfg_dir = tmp_path / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text(
        "audit:\n  capabilities:\n    - no-mcp\n", encoding="utf-8"
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.has_capability("no-mcp") is True
