"""Tests for PS-PATH-001 / PS-PATH-002 — config/PATH.yaml shape.

Covers the standalone checks and the cross-checks against the real
fixtures cited in the operator directive 2026-06-01:

  * paper-scitex-clew real BEFORE-state PATH.yaml — must trip both
    PS-PATH-001 (outer `PATH:` wrapper) AND PS-PATH-002 (raw
    string leaves).
  * The AFTER-state shape from PR #97 — must NOT trip either rule.

No mocks (NM001-003) — real temp repos built with `tmp_path`.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._audit import Violation
from scitex_dev._cli.audit._project._check_path_yaml import (
    check_ps_path_001_outer_wrapper,
    check_ps_path_002_bare_string_leaf,
)


# Real BEFORE-state fixture — verbatim copy of
# paper-scitex-clew/config/PATH.yaml at HEAD on 2026-06-01.
# Both wrapper AND bare-string leaves present, exactly the failure
# mode that bit the cohort runs.
_BEFORE_PATH_YAML = """\
# Timestamp: "2026-05-04"
# File: ./config/PATH.yaml

PATH:

  PAPER:    "./paper"
  CLEW:     "./clew"
  AGENTS:   "./agents"
  CONFIG:   "./config"
  DATA:     "./data"

  COHORT_A:
    ROOT:      "./data/cohort_a_corebench"
    SRC:       "./data/cohort_a_corebench/src"
    RAW:       f"./data/cohort_a_corebench/src/capsules/{capsule_id}.tar.gz"
"""


# Real AFTER-state fixture — matches the PR #97 canonical example
# (no outer wrapper, every value f-prefixed including static paths).
_AFTER_PATH_YAML = """\
# config/PATH.yaml — no outer ``PATH:`` wrapper, universal ``f"..."``

PAPER:    f"./paper"
CLEW:     f"./clew"
DATA:     f"./data"

COHORT_A:
  ROOT:      f"./data/cohort_a_corebench"
  SRC:       f"./data/cohort_a_corebench/src"
  RAW:       f"./data/cohort_a_corebench/src/capsules/{capsule_id}.tar.gz"
"""


def _write_path_yaml(repo: Path, content: str) -> Path:
    cfg = repo / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    target = cfg / "PATH.yaml"
    target.write_text(content)
    return target


def _rules_for_ps_path(repo: Path) -> list[Violation]:
    out: list = []
    check_ps_path_001_outer_wrapper(repo, Violation, out)
    check_ps_path_002_bare_string_leaf(repo, Violation, out)
    return out


# ── PS-PATH-001 ───────────────────────────────────────────────────────────


def test_ps_path_001_fires_on_outer_wrapper_real_fixture(tmp_path):
    # Arrange — real paper-scitex-clew BEFORE-state PATH.yaml.
    _write_path_yaml(tmp_path, _BEFORE_PATH_YAML)
    # Act
    out: list = []
    check_ps_path_001_outer_wrapper(tmp_path, Violation, out)
    # Assert
    codes = {v.rule for v in out}
    assert "PS-PATH-001" in codes


def test_ps_path_001_locates_wrapper_line(tmp_path):
    # Arrange
    _write_path_yaml(tmp_path, _BEFORE_PATH_YAML)
    # Act
    out: list = []
    check_ps_path_001_outer_wrapper(tmp_path, Violation, out)
    # Assert — the `PATH:` line is on line 4 in the fixture (after the
    # two comment lines and one blank). Allow tolerance of 1 line for
    # leading whitespace handling.
    ps_path_001 = [v for v in out if v.rule == "PS-PATH-001"][0]
    line_str = ps_path_001.where.rsplit(":", 1)[-1]
    assert line_str.isdigit()
    assert 1 <= int(line_str) <= 6


def test_ps_path_001_does_not_fire_on_after_fixture(tmp_path):
    # Arrange — canonical AFTER-state.
    _write_path_yaml(tmp_path, _AFTER_PATH_YAML)
    # Act
    out: list = []
    check_ps_path_001_outer_wrapper(tmp_path, Violation, out)
    # Assert
    codes = {v.rule for v in out}
    assert "PS-PATH-001" not in codes


def test_ps_path_001_noop_without_path_yaml(tmp_path):
    # Arrange — empty repo, no config/PATH.yaml
    # Act
    out: list = []
    check_ps_path_001_outer_wrapper(tmp_path, Violation, out)
    # Assert
    assert out == []


# ── PS-PATH-002 ───────────────────────────────────────────────────────────


def test_ps_path_002_fires_on_bare_strings_real_fixture(tmp_path):
    # Arrange — real BEFORE PATH.yaml (5 bare-string leaves + 1 f-string).
    _write_path_yaml(tmp_path, _BEFORE_PATH_YAML)
    # Act
    out: list = []
    check_ps_path_002_bare_string_leaf(tmp_path, Violation, out)
    # Assert — multiple bare-string leaves trip the rule.
    codes = [v.rule for v in out]
    assert codes.count("PS-PATH-002") >= 5


def test_ps_path_002_does_not_fire_on_after_fixture(tmp_path):
    # Arrange — canonical AFTER-state, every value f-prefixed.
    _write_path_yaml(tmp_path, _AFTER_PATH_YAML)
    # Act
    out: list = []
    check_ps_path_002_bare_string_leaf(tmp_path, Violation, out)
    # Assert
    codes = {v.rule for v in out}
    assert "PS-PATH-002" not in codes


def test_ps_path_002_accepts_both_quote_styles(tmp_path):
    # Arrange
    _write_path_yaml(
        tmp_path,
        'A: f"./a"\nB: f\'./b\'\nC: F"./c"\nD: F\'./d\'\n',
    )
    # Act
    out: list = []
    check_ps_path_002_bare_string_leaf(tmp_path, Violation, out)
    # Assert
    assert out == []


def test_ps_path_002_skips_dict_headers(tmp_path):
    # Arrange — `COHORT_A:` is a dict header, not a leaf.
    _write_path_yaml(
        tmp_path,
        'COHORT_A:\n  ROOT: f"./data/a"\n  SRC:  f"./data/a/src"\n',
    )
    # Act
    out: list = []
    check_ps_path_002_bare_string_leaf(tmp_path, Violation, out)
    # Assert
    assert out == []


def test_ps_path_002_flags_bare_quoted_string(tmp_path):
    # Arrange — quoted but no f-prefix is STILL a violation (the
    # eval()-on-bare-string SyntaxError is the failure mode).
    _write_path_yaml(tmp_path, 'CLEW: "./clew"\n')
    # Act
    out: list = []
    check_ps_path_002_bare_string_leaf(tmp_path, Violation, out)
    # Assert
    codes = {v.rule for v in out}
    assert "PS-PATH-002" in codes


def test_ps_path_002_skips_block_scalars(tmp_path):
    # Arrange — `|` and `>` block scalars are not evalable f-strings;
    # the rule prefers false negatives over false positives here.
    _write_path_yaml(
        tmp_path,
        "DESC: |\n  multi\n  line\nA: f\"./a\"\n",
    )
    # Act
    out: list = []
    check_ps_path_002_bare_string_leaf(tmp_path, Violation, out)
    # Assert
    assert out == []


# ── audit_project integration (JSON path) ────────────────────────────────


def test_audit_project_emits_ps_path_rules_in_json(tmp_path):
    """End-to-end: audit_project --json emits PS-PATH-001/002 records
    with `rule`, `where`, `detail`, `severity` keys consumable by the
    pre-tool-use hook downstream."""
    # Arrange — minimal research repo with the buggy PATH.yaml.
    import io
    import json
    from contextlib import redirect_stdout

    from scitex_dev._cli.audit._config import write_config
    from scitex_dev._cli.audit._project._audit import audit_project

    (tmp_path / ".scitex/dev").mkdir(parents=True)
    write_config(tmp_path, project_types=["research"])
    (tmp_path / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "scripts" / "analysis" / "01_x.py").write_text("x = 1\n")
    (tmp_path / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "tests" / "scripts" / "analysis" / "test_01_x.py").write_text(
        "def test_x():\n    assert True\n"
    )
    _write_path_yaml(tmp_path, _BEFORE_PATH_YAML)
    # Act
    buf = io.StringIO()
    with redirect_stdout(buf):
        audit_project("demo-research", repo=tmp_path, json_out=True, severity="warning")
    payload = json.loads(buf.getvalue())
    # Assert — both rules present, severity E recorded in the payload,
    # and the `where` field carries `<path>:<line>` shape.
    by_rule = {v["rule"]: v for v in payload["violations"]}
    assert "PS-PATH-001" in by_rule
    assert by_rule["PS-PATH-001"]["severity"] == "E"
    assert ":" in by_rule["PS-PATH-001"]["where"]
    ps_path_002_seen = [v for v in payload["violations"] if v["rule"] == "PS-PATH-002"]
    assert len(ps_path_002_seen) >= 5
    for v in ps_path_002_seen:
        assert v["severity"] == "E"
        assert ":" in v["where"]
