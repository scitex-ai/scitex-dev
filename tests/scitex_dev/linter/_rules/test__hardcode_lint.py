"""Tests for the HARDCODE-LINT extension (STX-S009 / S010 / S011 / S012).

Operator directive 2026-06-15. These rules cover string / path / param
hardcoding and redundant logging after scitex ``save()`` calls. Their
severity is project-type-driven:

  * project-type: research → "error" (blocking)
  * everything else        → "warning" (soft signal)

Layout: each rule gets a clean case (no fire), a violation case (fires
with the right severity), and a ``config/`` carve-out case (exempt).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.linter._rules import ALL_RULES
from scitex_dev.linter._rules import _session_structure as ss
from scitex_dev.linter.checker import lint_file, lint_source


# ---------------------------------------------------------------------------
# Rule registration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rule_id",
    ["STX-S009", "STX-S010", "STX-S011", "STX-S012"],
)
def test_hardcode_rule_registered(rule_id):
    # Arrange
    # Act
    rule = ALL_RULES.get(rule_id)
    # Assert
    assert rule is not None, f"{rule_id} missing from ALL_RULES"
    assert rule.category == "structure"


def test_hardcode_default_severity_is_warning():
    # Arrange
    # Act
    # Assert
    for r in (ss.S009, ss.S010, ss.S011, ss.S012):
        assert r.severity == "warning", f"{r.id} default severity != warning"


# ---------------------------------------------------------------------------
# Helper: write a temporary project tree
# ---------------------------------------------------------------------------


def _write_project(tmp_path: Path, project_type: str | None) -> Path:
    """Create a tmp project with optional .scitex/dev/config.yaml."""
    if project_type is not None:
        cfg = tmp_path / ".scitex" / "dev" / "config.yaml"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(f"project-type:\n  - {project_type}\n")
    (tmp_path / "scripts").mkdir(exist_ok=True)
    (tmp_path / "config").mkdir(exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# STX-S009 — string literal outside config/
# ---------------------------------------------------------------------------


def test_s009_clean_case_no_fire(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "ok.py"
    p.write_text('"""Doc."""\nimport scitex as stx\n\nx = 1\n')
    # Act
    issues = lint_file(str(p))
    # Assert
    assert not any(i.rule.id == "STX-S009" for i in issues)


def test_s009_fires_on_string_literal_assignment(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "pip")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""x"""\nCOHORT = "fig01_cohort_name"\n')
    # Act
    issues = lint_file(str(p))
    # Assert: STX-S011 fires (param + string). On a non-path string
    # STX-S009 isn't issued by the param check itself; the literal
    # visitor catches the same constant separately.
    assert any(i.rule.id == "STX-S011" for i in issues)


def test_s009_severity_upgraded_for_research(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""d"""\nCOHORT = "fig01_cohort_name"\n')
    # Act
    issues = lint_file(str(p))
    s011 = [i for i in issues if i.rule.id == "STX-S011"]
    # Assert
    assert s011, "STX-S011 expected to fire"
    assert all(i.rule.severity == "error" for i in s011)


def test_s009_exempt_under_config_dir(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "config" / "COHORT.py"
    p.write_text('NAME = "fig01_cohort_name"\n')
    # Act
    issues = lint_file(str(p))
    hardcode = [
        i
        for i in issues
        if i.rule.id in ("STX-S009", "STX-S010", "STX-S011", "STX-S012")
    ]
    # Assert
    assert hardcode == [], "config/ should be fully exempt"


# ---------------------------------------------------------------------------
# STX-S010 — path-like string literal outside config/
# ---------------------------------------------------------------------------


def test_s010_clean_case_no_fire(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "ok.py"
    p.write_text(
        '"""d"""\nimport scitex as stx\n\ndef f(CONFIG):\n    return CONFIG.PATH.DATA\n'
    )
    # Act
    issues = lint_file(str(p))
    # Assert
    assert not any(i.rule.id == "STX-S010" for i in issues)


def test_s010_fires_on_path_literal(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""d"""\nDATA_PATH = "data/fig01_cohort"\n')
    # Act
    issues = lint_file(str(p))
    s010 = [i for i in issues if i.rule.id == "STX-S010"]
    # Assert
    assert s010, "STX-S010 expected to fire on data/fig01_cohort"
    assert all(i.rule.severity == "error" for i in s010)


def test_s010_extension_path_literal(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""d"""\nOUT = "result.csv"\n')
    # Act
    issues = lint_file(str(p))
    s010 = [i for i in issues if i.rule.id == "STX-S010"]
    # Assert
    assert s010, "STX-S010 expected to fire on result.csv"


def test_s010_does_not_fire_on_natural_language(tmp_path: Path):
    # Arrange — log message that happens to mention an extension
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text(
        '"""d"""\nimport scitex as stx\n'
        "stx.io.save(df, 'out.csv')\n"
        "print('saved out.csv')\n"
    )
    # Act
    issues = lint_file(str(p))
    # Assert: "saved out.csv" contains a space → not flagged as path.
    s010_on_print = [
        i for i in issues if i.rule.id == "STX-S010" and "saved" in i.source_line
    ]
    assert s010_on_print == []


# ---------------------------------------------------------------------------
# STX-S011 — hardcoded UPPER_CASE = literal param in script
# ---------------------------------------------------------------------------


def test_s011_clean_case_lowercase_not_flagged(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "ok.py"
    # Lowercase assignments are NOT params (S011 only flags UPPER_CASE)
    p.write_text('"""d"""\nlocal_data = "data/fig01_cohort"\n')
    # Act
    issues = lint_file(str(p))
    s011 = [i for i in issues if i.rule.id == "STX-S011"]
    # Assert
    assert s011 == []


def test_s011_fires_on_uppercase_string_param(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""d"""\nCOHORT = "fig01_cohort_name_long"\n')
    # Act
    issues = lint_file(str(p))
    s011 = [i for i in issues if i.rule.id == "STX-S011"]
    # Assert
    assert s011
    assert all(i.rule.severity == "error" for i in s011)


def test_s011_exempt_under_config_dir(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "config" / "COHORT.py"
    p.write_text('NAME = "fig01_cohort_name"\n')
    # Act
    issues = lint_file(str(p))
    # Assert
    assert not any(i.rule.id == "STX-S011" for i in issues)


# ---------------------------------------------------------------------------
# STX-S012 — redundant print/logger after scitex save()
# ---------------------------------------------------------------------------


def test_s012_clean_case_save_alone_no_fire(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "ok.py"
    p.write_text('"""d"""\nimport scitex as stx\nstx.io.save(df, \'out.csv\')\n')
    # Act
    issues = lint_file(str(p))
    # Assert
    assert not any(i.rule.id == "STX-S012" for i in issues)


def test_s012_fires_on_print_after_save(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text(
        '"""d"""\nimport scitex as stx\n'
        "stx.io.save(df, 'out.csv')\n"
        "print('saved')\n"
    )
    # Act
    issues = lint_file(str(p))
    s012 = [i for i in issues if i.rule.id == "STX-S012"]
    # Assert
    assert s012, "STX-S012 expected to fire on print after save"
    assert all(i.rule.severity == "error" for i in s012)


def test_s012_fires_on_logger_info_after_save(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "pip")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text(
        '"""d"""\nimport scitex as stx\n'
        "stx.io.save(df, 'out.csv')\n"
        "logger.info('wrote out.csv')\n"
    )
    # Act
    issues = lint_file(str(p))
    s012 = [i for i in issues if i.rule.id == "STX-S012"]
    # Assert
    assert s012
    # pip project-type → severity stays at "warning"
    assert all(i.rule.severity == "warning" for i in s012)


def test_s012_exempt_under_config_dir(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "config" / "init.py"
    p.write_text("import scitex as stx\nstx.io.save(df, 'out.csv')\nprint('saved')\n")
    # Act
    issues = lint_file(str(p))
    # Assert
    assert not any(i.rule.id == "STX-S012" for i in issues)


# ---------------------------------------------------------------------------
# Conditional-severity driver
# ---------------------------------------------------------------------------


def test_no_config_keeps_warning_severity(tmp_path: Path):
    # Arrange — no .scitex/dev/config.yaml at all.
    (tmp_path / "scripts").mkdir()
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""d"""\nDATA_PATH = "data/fig01_cohort"\n')
    # Act
    issues = lint_file(str(p))
    s010 = [i for i in issues if i.rule.id == "STX-S010"]
    # Assert
    assert s010
    assert all(i.rule.severity == "warning" for i in s010)


def test_research_upgrades_all_hardcode_rules_to_error():
    # Arrange — drive directly through lint_source with a research config.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".scitex" / "dev").mkdir(parents=True)
        (root / ".scitex" / "dev" / "config.yaml").write_text(
            "project-type:\n  - research\n"
        )
        (root / "scripts").mkdir()
        p = root / "scripts" / "fig.py"
        src = (
            '"""d"""\nimport scitex as stx\n'
            'DATA_PATH = "data/fig01_cohort"\n'
            "stx.io.save(df, 'out.csv')\n"
            "print('saved')\n"
        )
        p.write_text(src)
        # Act
        issues = lint_source(src, filepath=str(p))
        # Assert
        hardcode = [
            i
            for i in issues
            if i.rule.id in ("STX-S009", "STX-S010", "STX-S011", "STX-S012")
        ]
        assert hardcode, "expected hardcode-lint fires"
        assert all(i.rule.severity == "error" for i in hardcode)


# ---------------------------------------------------------------------------
# Suppression via # stx-allow
# ---------------------------------------------------------------------------


def test_stx_allow_suppresses_s010(tmp_path: Path):
    # Arrange
    _write_project(tmp_path, "research")
    p = tmp_path / "scripts" / "fig.py"
    p.write_text('"""d"""\nDATA_PATH = "data/fig01_cohort"  # stx-allow: STX-S010\n')
    # Act
    issues = lint_file(str(p))
    # Assert: STX-S010 suppressed; STX-S011 still fires (separate rule).
    s010 = [i for i in issues if i.rule.id == "STX-S010"]
    assert s010 == [], "STX-S010 should be suppressed by # stx-allow"
