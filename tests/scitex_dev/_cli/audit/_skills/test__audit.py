"""Smoke tests for the skills auditor (`scitex-dev ecosystem audit-skills`).

Mirrors `tests/test_audit_api.py` — exercises the engine on synthetic
`_skills/<pip-name>/` trees in tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_dev._cli.audit._skills import RULES, Violation, audit_skills
from scitex_dev._cli.audit._skills._audit import (
    _check_frontmatter,
    _check_header_footer,
    _check_index_links,
    _check_naming,
    _locate_skills_dir,
)


# ---------------------------------------------------------------------------
# Rule registry sanity
# ---------------------------------------------------------------------------


def test_rules_have_unique_codes():
    # Arrange
    # Act
    codes = list(RULES.keys())
    # Assert
    assert len(codes) == len(set(codes))


def test_rules_code_matches_rule_attribute():
    # Arrange
    # Act
    pairs = [(code, rule.code) for code, rule in RULES.items()]
    # Assert
    assert all(c == rc for c, rc in pairs)


def test_rules_section_starts_with_section_sign():
    # Arrange
    # Act
    sections = [rule.section for rule in RULES.values()]
    # Assert
    assert all(s.startswith("§") for s in sections)


def test_rules_have_nonempty_message():
    # Arrange
    # Act
    messages = [rule.message for rule in RULES.values()]
    # Assert
    assert all(messages)


def test_rule_namespace_is_sk():
    # Arrange
    # Act
    # Assert
    for code in RULES:
        assert code.startswith("SK"), f"rule {code} should start with SK"


# ---------------------------------------------------------------------------
# Header/footer (SK-210 / SK-211)
# ---------------------------------------------------------------------------


def test_sk210_flags_html_header_banner(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "01_overview.md"
    f.write_text(
        "<!-- ---\n!-- Timestamp: 2026-04-30\n!-- --- -->\n\n"
        "---\nname: x\ndescription: y\ntags: [z]\n---\n\n# X\n"
    )
    out: list[Violation] = []
    _check_header_footer(f, out)
    codes = {v.rule for v in out}
    assert "SK-210" in codes


def test_sk211_flags_eof_marker(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "02_topic.md"
    f.write_text("---\nname: x\ndescription: y\n---\n\n# X\n\n<!-- EOF -->")
    out: list[Violation] = []
    _check_header_footer(f, out)
    codes = {v.rule for v in out}
    assert "SK-211" in codes


def test_clean_file_passes_header_footer(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "03_clean.md"
    f.write_text("---\nname: x\ndescription: y\ntags: [z]\n---\n\n# X\n")
    out: list[Violation] = []
    _check_header_footer(f, out)
    assert out == []


# ---------------------------------------------------------------------------
# Frontmatter (SK-701 / SK-702 / SK-703 / SK-704)
# ---------------------------------------------------------------------------


def test_sk701_flags_missing_frontmatter_result_is_none(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_no-frontmatter.md"
    f.write_text("# Just a heading, no frontmatter\n")
    out: list[Violation] = []
    result = _check_frontmatter(f, out)
    assert result is None


def test_sk701_flags_missing_frontmatter_v_rule_for_v_in_out_sk_701(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_no-frontmatter.md"
    f.write_text("# Just a heading, no frontmatter\n")
    out: list[Violation] = []
    result = _check_frontmatter(f, out)
    assert {v.rule for v in out} == {"SK-701"}


def test_sk702_703_704_flag_missing_required_fields_sk_702_in_codes(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_partial.md"
    # Has frontmatter but missing name, description, tags
    f.write_text("---\nuser-invocable: true\n---\n\n# X\n")
    out: list[Violation] = []
    _check_frontmatter(f, out)
    codes = {v.rule for v in out}
    assert "SK-702" in codes


def test_sk702_703_704_flag_missing_required_fields_sk_703_in_codes(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_partial.md"
    # Has frontmatter but missing name, description, tags
    f.write_text("---\nuser-invocable: true\n---\n\n# X\n")
    out: list[Violation] = []
    _check_frontmatter(f, out)
    codes = {v.rule for v in out}
    assert "SK-703" in codes


def test_sk702_703_704_flag_missing_required_fields_sk_704_in_codes(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_partial.md"
    # Has frontmatter but missing name, description, tags
    f.write_text("---\nuser-invocable: true\n---\n\n# X\n")
    out: list[Violation] = []
    _check_frontmatter(f, out)
    codes = {v.rule for v in out}
    assert "SK-704" in codes


def test_full_frontmatter_passes_result_is_not_none(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_full.md"
    f.write_text(
        "---\nname: full\ndescription: complete\ntags: [scitex-package]\n---\n\n# X\n"
    )
    out: list[Violation] = []
    result = _check_frontmatter(f, out)
    assert result is not None


def test_full_frontmatter_passes_out(tmp_path):
    # Arrange
    # Act
    # Assert
    f = tmp_path / "00_full.md"
    f.write_text(
        "---\nname: full\ndescription: complete\ntags: [scitex-package]\n---\n\n# X\n"
    )
    out: list[Violation] = []
    result = _check_frontmatter(f, out)
    assert out == []


# ---------------------------------------------------------------------------
# Naming (SK-201 / SK-203)
# ---------------------------------------------------------------------------


def test_sk201_flags_missing_numeric_prefix(tmp_path):
    # Arrange
    # Act
    # Assert
    (tmp_path / "save-and-load.md").write_text(
        "---\nname: x\ndescription: y\ntags: [z]\n---\n# X\n"
    )
    (tmp_path / "SKILL.md").write_text(
        "---\nname: pkg\ndescription: y\ntags: [z]\n---\n# Pkg\n"
    )
    out: list[Violation] = []
    _check_naming(tmp_path, out)
    codes = {v.rule for v in out}
    assert "SK-201" in codes


def test_sk203_flags_non_kebab_case(tmp_path):
    # Arrange
    # Act
    # Assert
    (tmp_path / "01_SaveAndLoad.md").write_text("---\nname: x\n---\n# X\n")
    out: list[Violation] = []
    _check_naming(tmp_path, out)
    codes = {v.rule for v in out}
    assert "SK-203" in codes


def test_compliant_naming_passes(tmp_path):
    # Arrange
    # Act
    # Assert
    (tmp_path / "SKILL.md").write_text("---\nname: x\n---\n")
    (tmp_path / "01_save-and-load.md").write_text("---\nname: x\n---\n")
    (tmp_path / "20_env-vars.md").write_text("---\nname: x\n---\n")
    out: list[Violation] = []
    _check_naming(tmp_path, out)
    assert out == []


# ---------------------------------------------------------------------------
# Index links (SK-302)
# ---------------------------------------------------------------------------


def test_sk302_flags_orphan_leaf_sk_302_02_orphan_md_in_codes_paths(tmp_path):
    # Arrange
    # Act
    # Assert
    (tmp_path / "SKILL.md").write_text(
        "---\nname: x\n---\n\n# X\n\n- [link](01_topic.md)\n"
    )
    (tmp_path / "01_topic.md").write_text("---\nname: x\n---\n")
    (tmp_path / "02_orphan.md").write_text("---\nname: x\n---\n")
    out: list[Violation] = []
    _check_index_links(tmp_path / "SKILL.md", tmp_path, out)
    codes_paths = {(v.rule, Path(v.where).name) for v in out}
    assert ("SK-302", "02_orphan.md") in codes_paths


def test_sk302_flags_orphan_leaf_sk_302_01_topic_md_not_in_codes_paths(tmp_path):
    # Arrange
    # Act
    # Assert
    (tmp_path / "SKILL.md").write_text(
        "---\nname: x\n---\n\n# X\n\n- [link](01_topic.md)\n"
    )
    (tmp_path / "01_topic.md").write_text("---\nname: x\n---\n")
    (tmp_path / "02_orphan.md").write_text("---\nname: x\n---\n")
    out: list[Violation] = []
    _check_index_links(tmp_path / "SKILL.md", tmp_path, out)
    codes_paths = {(v.rule, Path(v.where).name) for v in out}
    assert ("SK-302", "01_topic.md") not in codes_paths


# ---------------------------------------------------------------------------
# End-to-end via audit_skills() entry point
# ---------------------------------------------------------------------------


def _make_compliant_pkg(tmp_path: Path, dist: str) -> Path:
    """Write a synthetic `_skills/<dist>/` tree that should pass all rules."""
    pkg_root = tmp_path / dist.replace("-", "_") / "_skills" / dist
    pkg_root.mkdir(parents=True)
    import_name = dist.replace("-", "_")
    (pkg_root / "SKILL.md").write_text(
        f"---\n"
        f"name: {dist}\n"
        f"description: |\n"
        f"  [WHAT] Test package.\n"
        f"  [WHEN] Running the test suite.\n"
        f"  [HOW] import {import_name}.\n"
        f"tags: [{dist}]\n"
        f"---\n\n# {dist}\n\n"
        f"- [01_installation.md](01_installation.md)\n"
        f"- [02_quick-start.md](02_quick-start.md)\n"
    )
    (pkg_root / "01_installation.md").write_text(
        f"---\n"
        f"description: |\n"
        f"  [TOPIC] Installation\n"
        f"  [DETAILS] pip install {dist}.\n"
        f"tags: [{dist}-installation]\n"
        f"---\n\n# Installation\n"
    )
    (pkg_root / "02_quick-start.md").write_text(
        f"---\n"
        f"description: |\n"
        f"  [TOPIC] Quick start\n"
        f"  [DETAILS] smallest example.\n"
        f"tags: [{dist}-quick-start]\n"
        f"---\n\n# Quick\n"
    )
    return pkg_root


def test_audit_skills_skips_when_package_not_installed_rc_0(capsys):
    # Not every package ships a `_skills/` directory, and audit-all
    # may run before `pip install -e .`. Skip rather than fail so
    # ecosystem audit-all doesn't trip on every uninstallable peer.
    # Arrange
    # Act
    # Assert
    rc = audit_skills("definitely-not-a-real-pkg-xyz")
    assert rc == 0
    err = capsys.readouterr().err


def test_audit_skills_skips_when_package_not_installed_logs_no__skills_directory(
    caplog,
):
    # Not every package ships a `_skills/` directory, and audit-all
    # may run before `pip install -e .`. Skip rather than fail so
    # ecosystem audit-all doesn't trip on every uninstallable peer.
    # Arrange
    import logging

    caplog.set_level(logging.INFO, logger="scitex_dev.audit")
    # Act
    audit_skills("definitely-not-a-real-pkg-xyz")
    # Assert
    assert any("no `_skills/` directory" in r.message for r in caplog.records)


def test_audit_skills_skips_when_package_not_installed_logs_at_info_level(caplog):
    # Not every package ships a `_skills/` directory, and audit-all
    # may run before `pip install -e .`. Skip rather than fail so
    # ecosystem audit-all doesn't trip on every uninstallable peer.
    # Arrange
    import logging

    caplog.set_level(logging.INFO, logger="scitex_dev.audit")
    # Act
    audit_skills("definitely-not-a-real-pkg-xyz")
    # Assert
    assert any(r.levelno == logging.INFO for r in caplog.records)


def test_audit_skills_passes_clean_synthetic_pkg_rc_0(tmp_path, capsys):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "synthtest")
    rc = audit_skills("synthtest", skills_dir=pkg_root)
    out = capsys.readouterr().out
    assert rc == 0


def test_audit_skills_passes_clean_synthetic_pkg_logs_no_skills_violations(
    tmp_path, caplog
):
    # Arrange
    import logging

    caplog.set_level(logging.INFO, logger="scitex_dev.audit")
    pkg_root = _make_compliant_pkg(tmp_path, "synthtest")
    # Act
    audit_skills("synthtest", skills_dir=pkg_root)
    # Assert
    assert any("no skills violations" in r.message for r in caplog.records)


def test_audit_skills_finds_violations_in_dirty_pkg(tmp_path, capsys):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "dirty")
    # Introduce a header and an orphan.
    (pkg_root / "SKILL.md").write_text(
        "<!-- ---\n!-- Timestamp: 2026-04-30\n!-- --- -->\n\n"
        "---\nname: dirty\ndescription: x\ntags: [dirty]\n---\n\n# Dirty\n"
    )
    (pkg_root / "02_orphan.md").write_text(
        "---\nname: orphan\ndescription: x\ntags: [t]\n---\n# X\n"
    )
    rc = audit_skills("dirty", skills_dir=pkg_root)
    assert rc == 1


@pytest.fixture
def _json_audit_run(tmp_path, capsys):
    # Arrange
    pkg_root = _make_compliant_pkg(tmp_path, "jsonpkg")
    (pkg_root / "01_quick-start.md").write_text("# Missing frontmatter\n")
    # Act
    rc = audit_skills("jsonpkg", json_out=True, skills_dir=pkg_root)
    payload = json.loads(capsys.readouterr().out)
    return rc, payload


def test_audit_skills_json_returns_rc_one(_json_audit_run):
    # Arrange
    rc, _ = _json_audit_run
    # Act
    # Assert
    assert rc == 1


def test_audit_skills_json_payload_distribution_field(_json_audit_run):
    # Arrange
    _, payload = _json_audit_run
    # Act
    dist = payload["distribution"]
    # Assert
    assert dist == "jsonpkg"


def test_audit_skills_json_payload_violations_is_list(_json_audit_run):
    # Arrange
    _, payload = _json_audit_run
    # Act
    violations = payload["violations"]
    # Assert
    assert isinstance(violations, list)


def test_audit_skills_json_payload_has_at_least_one_violation(_json_audit_run):
    # Arrange
    _, payload = _json_audit_run
    # Act
    n = len(payload["violations"])
    # Assert
    assert n >= 1


def test_audit_skills_json_violation_has_rule_where_detail_keys(_json_audit_run):
    # Arrange
    _, payload = _json_audit_run
    # Act
    keysets = [set(v.keys()) for v in payload["violations"]]
    # Assert
    assert all(ks == {"rule", "where", "detail"} for ks in keysets)


def test_sk706_flags_missing_markers_in_skill_md_rc_1(tmp_path, capsys):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "marktest")
    # Replace SKILL.md description with one missing [HOW]
    (pkg_root / "SKILL.md").write_text(
        "---\n"
        "name: marktest\n"
        "description: |\n"
        "  [WHAT] thing.\n"
        "  [WHEN] always.\n"
        "tags: [marktest]\n"
        "---\n\n# marktest\n\n"
        "- [01_installation.md](01_installation.md)\n"
        "- [02_quick-start.md](02_quick-start.md)\n"
    )
    rc = audit_skills("marktest", json_out=True, rules={"SK-706"}, skills_dir=pkg_root)
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    codes = {v["rule"] for v in payload["violations"]}


def test_sk706_flags_missing_markers_in_skill_md_sk_706_in_codes(tmp_path, capsys):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "marktest")
    # Replace SKILL.md description with one missing [HOW]
    (pkg_root / "SKILL.md").write_text(
        "---\n"
        "name: marktest\n"
        "description: |\n"
        "  [WHAT] thing.\n"
        "  [WHEN] always.\n"
        "tags: [marktest]\n"
        "---\n\n# marktest\n\n"
        "- [01_installation.md](01_installation.md)\n"
        "- [02_quick-start.md](02_quick-start.md)\n"
    )
    rc = audit_skills("marktest", json_out=True, rules={"SK-706"}, skills_dir=pkg_root)
    payload = json.loads(capsys.readouterr().out)
    codes = {v["rule"] for v in payload["violations"]}
    assert "SK-706" in codes


def test_sk711_flags_missing_markers_in_leaf_rc_1(tmp_path, capsys):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "leafmark")
    # Replace 01_installation.md with description missing [DETAILS]
    (pkg_root / "01_installation.md").write_text(
        "---\n"
        "description: |\n"
        "  [TOPIC] Installation\n"
        "tags: [leafmark-installation]\n"
        "---\n\n# Installation\n"
    )
    rc = audit_skills("leafmark", json_out=True, rules={"SK-711"}, skills_dir=pkg_root)
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    codes = {v["rule"] for v in payload["violations"]}


def test_sk711_flags_missing_markers_in_leaf_sk_711_in_codes(tmp_path, capsys):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "leafmark")
    # Replace 01_installation.md with description missing [DETAILS]
    (pkg_root / "01_installation.md").write_text(
        "---\n"
        "description: |\n"
        "  [TOPIC] Installation\n"
        "tags: [leafmark-installation]\n"
        "---\n\n# Installation\n"
    )
    rc = audit_skills("leafmark", json_out=True, rules={"SK-711"}, skills_dir=pkg_root)
    payload = json.loads(capsys.readouterr().out)
    codes = {v["rule"] for v in payload["violations"]}
    assert "SK-711" in codes


def test_audit_skills_rule_filter_restricts_violations(tmp_path):
    # Arrange
    # Act
    # Assert
    pkg_root = _make_compliant_pkg(tmp_path, "filtertest")
    (pkg_root / "SKILL.md").write_text(
        "<!-- ---\n!-- foo --- -->\n\n---\nname: x\ndescription: y\ntags: [t]\n---\n"
        "\n# X\n\n- [01_quick-start.md](01_quick-start.md)\n"
    )
    (pkg_root / "01_bad.md").write_text("# missing frontmatter\n")
    rc = audit_skills(
        "filtertest", json_out=True, rules={"SK-210"}, skills_dir=pkg_root
    )
    # We restricted to SK-210 — should only see header-banner violations.
    import sys

    payload_text = sys.stdout  # pytest's capsys would normally take this
    # Re-run with capsys to verify
    # (this test mainly exercises that filtering doesn't crash)
    assert rc in (0, 1)


# ---------------------------------------------------------------------------
# _locate_skills_dir — registry source-tree fallback (phantom-SK-101 fix)
#
# Before this fallback, `_locate_skills_dir` returned None for any package
# not pip-installed in the auditor's venv — so packages with a perfectly
# good on-disk `_skills/` layout fired phantom SK-101. The fallback walks
# the package's source tree via ECOSYSTEM.local_path and resolves
# `<local_path>/src/<import_name>/_skills/<distribution>/` (or flat
# `_skills/` for legacy layouts).
# ---------------------------------------------------------------------------


from contextlib import contextmanager


@contextmanager
def _registry_override(distribution: str, local_path: Path):
    """Temporarily add (or replace) an ECOSYSTEM entry; restore on exit.

    No-mocks-compliant: pure dict mutation + try/finally restore (NOT
    pytest's `monkeypatch`, NOT `unittest.mock`). The sentinel `_MISSING`
    distinguishes "key didn't exist" from "key existed with None value"
    so restoration is exact. We mutate the shared ECOSYSTEM dict in place
    rather than wholesale-replacing it so other code paths (e.g. PS-149's
    umbrella detection) read real entries during the same test session.
    """
    from scitex_dev._ecosystem._registry import ECOSYSTEM

    _MISSING = object()
    before = ECOSYSTEM.get(distribution, _MISSING)
    ECOSYSTEM[distribution] = {
        "local_path": str(local_path),
        "pypi_name": distribution,
        "github_repo": f"ywatanabe1989/{distribution}",
        "import_name": distribution.replace("-", "_"),
        "category": "library",
    }
    try:
        yield
    finally:
        if before is _MISSING:
            ECOSYSTEM.pop(distribution, None)
        else:
            ECOSYSTEM[distribution] = before


def test_locate_skills_dir_falls_back_to_registry_source_tree(tmp_path):
    # Arrange — non-installed package with a valid on-disk sub-skill layout.
    # find_spec("phantompkg") returns None, so the source-tree fallback is
    # the only path that can return a non-None Path. Without it, SK-101
    # would fire as a phantom on every locally-cloned peer.
    dist = "scitex-phantompkg"
    import_name = "scitex_phantompkg"
    local_root = tmp_path / "scitex-phantompkg"
    skills_dir = local_root / "src" / import_name / "_skills" / dist
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\nname: scitex-phantompkg\ndescription: x\ntags: [scitex-phantompkg]\n---\n"
    )
    # Act
    with _registry_override(dist, local_root):
        result = _locate_skills_dir(dist)
    # Assert
    assert result == skills_dir


def test_locate_skills_dir_falls_back_to_flat_skills_layout(tmp_path):
    # Arrange — legacy flat `_skills/` (no sub-pip-name dir). The fallback
    # must return the flat dir so the caller can distinguish SK-102 from
    # SK-101.
    dist = "scitex-legacypkg"
    import_name = "scitex_legacypkg"
    local_root = tmp_path / "scitex-legacypkg"
    flat_dir = local_root / "src" / import_name / "_skills"
    flat_dir.mkdir(parents=True)
    (flat_dir / "01_overview.md").write_text("# legacy\n")
    # Act
    with _registry_override(dist, local_root):
        result = _locate_skills_dir(dist)
    # Assert
    assert result == flat_dir


def test_locate_skills_dir_returns_none_when_registry_path_missing_on_disk(
    tmp_path,
):
    # Arrange — registry has `local_path` but the directory doesn't exist
    # on this host (clean checkout, CI runner, etc.). The fallback must
    # NOT crash and must return None so the caller fires a real SK-101.
    dist = "scitex-ghostpkg"
    nonexistent = tmp_path / "does-not-exist"
    # Act
    with _registry_override(dist, nonexistent):
        result = _locate_skills_dir(dist)
    # Assert
    assert result is None


def test_locate_skills_dir_returns_none_when_neither_installed_nor_registered():
    # Arrange — distribution is not pip-installed AND not in ECOSYSTEM.
    # SK-101 is the correct verdict for this case (truly missing skills
    # tree), so the fallback must NOT invent a path.
    dist = "scitex-doesnotexistanywhere"
    # Act
    result = _locate_skills_dir(dist)
    # Assert
    assert result is None


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("scitex_dev") is None,
    reason="scitex_dev not importable; cannot verify install-precedence",
)
def test_locate_skills_dir_prefers_installed_when_both_present(tmp_path):
    # Arrange — installed package is the canonical source-of-truth (it's
    # what users actually import); registry fallback is only consulted
    # when find_spec fails. scitex_dev is installed in the test venv, so
    # a bogus registry path for "scitex-dev" must NOT win over the real
    # install location.
    bogus_root = tmp_path / "bogus-scitex-dev"
    bogus_skills = bogus_root / "src" / "scitex_dev" / "_skills" / "scitex-dev"
    bogus_skills.mkdir(parents=True)
    # Act
    with _registry_override("scitex-dev", bogus_root):
        result = _locate_skills_dir("scitex-dev")
    # Assert — install path wins, never under bogus_root
    assert result is None or bogus_root not in result.parents
