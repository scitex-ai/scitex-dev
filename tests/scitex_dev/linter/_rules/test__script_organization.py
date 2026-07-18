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
    _is_verb_token,
    _load_verb_lexicon,
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


# --------------------------------------------------------------------------
# Verb lexicon (S010 v2 — operator directive 2026-07-02: a real verb lexicon,
# not a curated whitelist). Regression fixture = the first-tokens the v1
# whitelist wrongly flagged on neurovista.
# --------------------------------------------------------------------------

# The 17 legitimate imperative first-tokens neurovista's scripts/ used that
# the v1 whitelist flagged as non-verbs (incl. the British-spelling
# ``analyse``, the re-derived ``recompute``/``rerender``, and the coined
# tech verb ``symlink``).
NEUROVISTA_FALSE_POSITIVE_LEMMAS = (
    "analyse", "compact", "compose", "compress", "define", "extract",
    "migrate", "monitor", "populate", "recompute", "register", "rerender",
    "resolve", "resume", "select", "symlink", "translate",
)


def test_lexicon_loads_thousands_of_lemmas():
    # Arrange
    lexicon = _load_verb_lexicon()
    # Act
    count = len(lexicon)
    # Assert
    assert count > 5000


def test_lexicon_contains_no_comment_lines():
    # Arrange
    lexicon = _load_verb_lexicon()
    # Act
    commentish = [w for w in lexicon if w.startswith("#") or " " in w]
    # Assert
    assert commentish == []


def test_neurovista_false_positive_lemmas_all_read_as_verbs():
    # Arrange
    extra = set(DEFAULT_SCRIPT_VERBS)
    # Act
    rejected = [
        t for t in NEUROVISTA_FALSE_POSITIVE_LEMMAS
        if not _is_verb_token(t, extra)
    ]
    # Assert
    assert rejected == [], f"still flagged as non-verbs: {rejected}"


def test_neurovista_false_positive_filenames_pass_s010_end_to_end():
    # Arrange
    cfg = _research_cfg()
    # Act
    flagged = [
        t for t in NEUROVISTA_FALSE_POSITIVE_LEMMAS
        if "STX-S010" in _ids(lint_source(_SRC, f"scripts/pac/{t}_thing.py", cfg))
    ]
    # Assert
    assert flagged == [], f"S010 still fires end-to-end for: {flagged}"


def test_british_spelling_analyse_is_a_verb():
    # Arrange
    token = "analyse"
    # Act
    ok = _is_verb_token(token, set())
    # Assert
    assert ok is True


def test_re_prefixed_derivation_recompute_is_a_verb():
    # Arrange — "recompute" is not a WordNet lemma; "compute" is.
    token = "recompute"
    # Act
    ok = _is_verb_token(token, set())
    # Assert
    assert ok is True


def test_short_re_word_is_not_stripped_to_a_verb():
    # Arrange — "redo" IS a lexicon verb itself, but a junk token like "rex"
    # must not pass via the re- stripping path (len guard).
    token = "rex"
    # Act
    ok = _is_verb_token(token, set())
    # Assert
    assert ok is False


def test_noun_token_analysis_is_still_not_a_verb():
    # Arrange — the rule must still catch noun-named scripts.
    token = "analysis"
    # Act
    ok = _is_verb_token(token, set())
    # Assert
    assert ok is False


def test_noun_filename_still_flags_s010_with_lexicon():
    # Arrange
    cfg = _research_cfg()
    # Act
    issues = lint_source(_SRC, "scripts/pac/dataset_thing.py", cfg)
    # Assert
    assert "STX-S010" in _ids(issues)


def test_config_extension_still_wins_over_lexicon_absence():
    # Arrange — a project coinage neither WordNet nor the defaults know.
    cfg = _research_cfg(script_verb_prefixes=["fooify"])
    # Act
    issues = lint_source(_SRC, "scripts/pac/fooify_thing.py", cfg)
    # Assert
    assert "STX-S010" not in _ids(issues)
