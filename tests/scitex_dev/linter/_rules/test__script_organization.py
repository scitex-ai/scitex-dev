"""Tests for STX-S009 / STX-S010 research script-organization rules.

These are PATH/FILENAME rules, research-gated and default WARNING. They fire
on files under a configured ``script_dir`` (which ``is_script()`` excludes),
so the tests drive the whole ``lint_source`` path with an explicit research
config and assert on the emitted rule ids/severities. No mocks — real config,
real checker.
"""

from __future__ import annotations

from scitex_dev.linter.checker import lint_source
from scitex_dev.linter.config import LinterConfig
from scitex_dev.linter._rules._script_organization import (
    DEFAULT_SCRIPT_VERBS,
    _first_token,
)

# Minimal, always-parseable script body — S009/S010 are path/name based, so
# the content is irrelevant beyond "it parses".
_SRC = "x = 1\n"


def _research_cfg(**overrides) -> LinterConfig:
    base = dict(project_types=["research"], script_dirs=["scripts"])
    base.update(overrides)
    return LinterConfig(**base)


def _ids(issues) -> set:
    return {i.rule.id for i in issues}


def _sev_of(issues, rule_id):
    for i in issues:
        if i.rule.id == rule_id:
            return i.rule.severity
    return None


# --------------------------------------------------------------------------
# STX-S009 — flat scripts/ vs domain-grouped
# --------------------------------------------------------------------------


def test_flat_verb_script_flags_s009():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/calc_pac.py", cfg)
    # Assert
    assert "STX-S009" in _ids(issues)


def test_flat_verb_script_does_not_flag_s010():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/calc_pac.py", cfg)
    # Assert
    assert "STX-S010" not in _ids(issues)


def test_grouped_verb_script_is_clean_of_s009():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/pac/calc_pac.py", cfg)
    # Assert
    assert "STX-S009" not in _ids(issues)


def test_grouped_verb_script_is_clean_of_s010():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/pac/calc_pac.py", cfg)
    # Assert
    assert "STX-S010" not in _ids(issues)


def test_deeply_grouped_script_is_clean_of_s009():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/pac/sub/calc_pac.py", cfg)
    # Assert
    assert "STX-S009" not in _ids(issues)


def test_absolute_path_flat_script_flags_s009():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "/home/u/proj/scripts/calc_pac.py", cfg)
    # Assert
    assert "STX-S009" in _ids(issues)


def test_min_depth_two_flags_single_domain_dir():
    # Arrange
    cfg = _research_cfg(script_domain_min_depth=2)
    # Act
    issues = lint_source(_SRC, "scripts/pac/calc_pac.py", cfg)
    # Assert
    assert "STX-S009" in _ids(issues)


def test_min_depth_two_passes_two_domain_dirs():
    # Arrange
    cfg = _research_cfg(script_domain_min_depth=2)
    # Act
    issues = lint_source(_SRC, "scripts/pac/sub/calc_pac.py", cfg)
    # Assert
    assert "STX-S009" not in _ids(issues)


# --------------------------------------------------------------------------
# STX-S010 — verb-first filename
# --------------------------------------------------------------------------


def test_grouped_noun_script_flags_s010():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/pac/analysis.py", cfg)
    # Assert
    assert "STX-S010" in _ids(issues)


def test_grouped_noun_script_does_not_flag_s009():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/pac/analysis.py", cfg)
    # Assert
    assert "STX-S009" not in _ids(issues)


def test_flat_noun_script_flags_s009():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert "STX-S009" in _ids(issues)


def test_flat_noun_script_flags_s010():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert "STX-S010" in _ids(issues)


def test_custom_verb_prefix_suppresses_s010():
    # Arrange
    cfg = _research_cfg(script_verb_prefixes=["foobar"])
    # Act
    issues = lint_source(_SRC, "scripts/pac/foobar_thing.py", cfg)
    # Assert
    assert "STX-S010" not in _ids(issues)


# --------------------------------------------------------------------------
# Exemptions & gating
# --------------------------------------------------------------------------


def test_dunder_files_are_exempt_from_org_rules():
    # Arrange
    cfg = _research_cfg()
    org_ids = {"STX-S009", "STX-S010"}
    # Act
    hits = {
        name: _ids(lint_source(_SRC, f"scripts/{name}", cfg)) & org_ids
        for name in ("__init__.py", "__main__.py")
    }
    # Assert
    assert hits == {"__init__.py": set(), "__main__.py": set()}


def test_conftest_file_is_exempt_from_org_rules():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/conftest.py", cfg)
    # Assert
    assert _ids(issues) & {"STX-S009", "STX-S010"} == set()


def test_custom_exempt_name_suppresses_org_rules():
    # Arrange
    cfg = _research_cfg(script_org_exempt=["legacy.py"])
    # Act
    issues = lint_source(_SRC, "scripts/legacy.py", cfg)
    # Assert
    assert _ids(issues) & {"STX-S009", "STX-S010"} == set()


def test_custom_exempt_list_keeps_builtin_dunder_exemption():
    # Arrange
    cfg = _research_cfg(script_org_exempt=["legacy.py"])
    # Act
    issues = lint_source(_SRC, "scripts/__init__.py", cfg)
    # Assert
    assert _ids(issues) & {"STX-S009", "STX-S010"} == set()


def test_non_research_project_does_not_fire_org_rules():
    # Arrange
    cfg = LinterConfig(project_types=[], script_dirs=["scripts"])
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert _ids(issues) & {"STX-S009", "STX-S010"} == set()


def test_file_outside_script_dir_does_not_fire_org_rules():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "notebooks/analysis.py", cfg)
    # Assert
    assert _ids(issues) & {"STX-S009", "STX-S010"} == set()


def test_non_python_file_does_not_fire_org_rules():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/README.md", cfg)
    # Assert
    assert _ids(issues) & {"STX-S009", "STX-S010"} == set()


# --------------------------------------------------------------------------
# Severity: default WARNING, per_rule_severity escalates to ERROR
# --------------------------------------------------------------------------


def test_s009_default_severity_is_warning():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert _sev_of(issues, "STX-S009") == "warning"


def test_s010_default_severity_is_warning():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert _sev_of(issues, "STX-S010") == "warning"


def test_per_rule_severity_escalates_s009_to_error():
    # Arrange
    cfg = _research_cfg(per_rule_severity={"STX-S009": "error"})
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert _sev_of(issues, "STX-S009") == "error"


def test_disable_suppresses_only_the_named_rule():
    # Arrange
    cfg = _research_cfg(disable=["STX-S009"])
    # Act
    issues = lint_source(_SRC, "scripts/analysis.py", cfg)
    # Assert
    assert "STX-S009" not in _ids(issues) and "STX-S010" in _ids(issues)


# --------------------------------------------------------------------------
# Helper unit coverage
# --------------------------------------------------------------------------


def test_first_token_splits_on_underscore():
    # Arrange
    stem = "calc_pac"
    # Act
    token = _first_token(stem)
    # Assert
    assert token == "calc"


def test_first_token_splits_on_dash():
    # Arrange
    stem = "plot-raster"
    # Act
    token = _first_token(stem)
    # Assert
    assert token == "plot"


def test_first_token_of_empty_stem_is_empty():
    # Arrange
    stem = ""
    # Act
    token = _first_token(stem)
    # Assert
    assert token == ""


def test_default_verbs_set_is_nonempty():
    # Arrange / Act done at import
    # Act
    count = len(DEFAULT_SCRIPT_VERBS)
    # Assert
    assert count > 0


def test_default_verbs_are_all_lowercase():
    # Arrange
    verbs = DEFAULT_SCRIPT_VERBS
    # Act
    all_lower = all(v == v.lower() for v in verbs)
    # Assert
    assert all_lower is True
