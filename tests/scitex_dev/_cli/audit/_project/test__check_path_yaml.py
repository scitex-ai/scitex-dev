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

import pytest

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


def _ps_path_001_where_line(repo: Path) -> str:
    """Arrange+Act helper: write BEFORE fixture, run rule, return line suffix."""
    _write_path_yaml(repo, _BEFORE_PATH_YAML)
    out: list = []
    check_ps_path_001_outer_wrapper(repo, Violation, out)
    ps_path_001 = [v for v in out if v.rule == "PS-PATH-001"][0]
    return ps_path_001.where.rsplit(":", 1)[-1]


def test_ps_path_001_where_carries_numeric_line(tmp_path):
    # Arrange
    # (BEFORE fixture + rule invocation delegated to helper)
    # Act
    line_str = _ps_path_001_where_line(tmp_path)
    # Assert
    assert line_str.isdigit()


def test_ps_path_001_locates_wrapper_line_in_range(tmp_path):
    # Arrange
    # (BEFORE fixture + rule invocation delegated to helper)
    # The `PATH:` line is on line 4 in the fixture (after the two
    # comment lines and one blank). Allow tolerance of 1 line for
    # leading whitespace handling.
    # Act
    line_str = _ps_path_001_where_line(tmp_path)
    # Assert
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


def _build_buggy_path_yaml_research_repo(repo: Path) -> None:
    """Arrange helper: minimal research repo with buggy BEFORE PATH.yaml."""
    from scitex_dev._cli.audit._config import write_config

    (repo / ".scitex/dev").mkdir(parents=True)
    write_config(repo, project_types=["research"])
    (repo / "scripts" / "analysis").mkdir(parents=True)
    (repo / "scripts" / "analysis" / "01_x.py").write_text("x = 1\n")
    (repo / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (repo / "tests" / "scripts" / "analysis" / "test_01_x.py").write_text(
        "def test_x():\n    assert True\n"
    )
    _write_path_yaml(repo, _BEFORE_PATH_YAML)


def _run_audit_project_json(repo: Path) -> dict:
    """Act helper: run audit_project --json and return payload."""
    import io
    import json
    from contextlib import redirect_stdout

    from scitex_dev._cli.audit._project._audit import audit_project

    buf = io.StringIO()
    with redirect_stdout(buf):
        audit_project("demo-research", repo=repo, json_out=True, severity="warning")
    return json.loads(buf.getvalue())


@pytest.fixture
def audit_payload_with_before_path_yaml(tmp_path):
    """Shared Arrange+Act: buggy PATH.yaml research repo audit payload.

    End-to-end: audit_project --json emits PS-PATH-001/002 records
    with `rule`, `where`, `detail`, `severity` keys consumable by the
    pre-tool-use hook downstream.
    """
    _build_buggy_path_yaml_research_repo(tmp_path)
    return _run_audit_project_json(tmp_path)


def test_audit_project_emits_ps_path_001(audit_payload_with_before_path_yaml):
    # Arrange (shared via fixture)
    payload = audit_payload_with_before_path_yaml
    # Act
    by_rule = {v["rule"]: v for v in payload["violations"]}
    # Assert
    assert "PS-PATH-001" in by_rule


def test_audit_project_records_ps_path_001_severity_e(
    audit_payload_with_before_path_yaml,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_before_path_yaml
    # Act
    by_rule = {v["rule"]: v for v in payload["violations"]}
    # Assert
    assert by_rule["PS-PATH-001"]["severity"] == "E"


def test_audit_project_ps_path_001_where_has_path_line_shape(
    audit_payload_with_before_path_yaml,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_before_path_yaml
    # Act
    by_rule = {v["rule"]: v for v in payload["violations"]}
    # Assert — `where` field carries `<path>:<line>` shape.
    assert ":" in by_rule["PS-PATH-001"]["where"]


def test_audit_project_emits_at_least_five_ps_path_002(
    audit_payload_with_before_path_yaml,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_before_path_yaml
    # Act
    ps_path_002_seen = [v for v in payload["violations"] if v["rule"] == "PS-PATH-002"]
    # Assert — BEFORE fixture has 5 bare-string leaves.
    assert len(ps_path_002_seen) >= 5


def test_audit_project_all_ps_path_002_records_have_severity_e(
    audit_payload_with_before_path_yaml,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_before_path_yaml
    # Act
    ps_path_002_seen = [v for v in payload["violations"] if v["rule"] == "PS-PATH-002"]
    severities = {v["severity"] for v in ps_path_002_seen}
    # Assert — every PS-PATH-002 record is severity E.
    assert severities == {"E"}


def test_audit_project_all_ps_path_002_records_have_path_line_where(
    audit_payload_with_before_path_yaml,
):
    # Arrange (shared via fixture)
    payload = audit_payload_with_before_path_yaml
    # Act
    ps_path_002_seen = [v for v in payload["violations"] if v["rule"] == "PS-PATH-002"]
    wheres_with_colon = [v for v in ps_path_002_seen if ":" in v["where"]]
    # Assert — every record's `where` carries `<path>:<line>` shape.
    assert len(wheres_with_colon) == len(ps_path_002_seen)


# ---------------------------------------------------------------------------
# Worktree-checkout skip — the file walker must never treat
# `.worktrees/` or `.claude/worktrees/` paths as canonical source.
# Lead-approved 2026-06-07 after PR #130 (worktree-gc) surfaced PS-PATH-001
# fires from stale operator worktree checkouts on scitex-dev develop.
# ---------------------------------------------------------------------------


from scitex_dev._cli.audit._project._check_path_yaml import (  # noqa: E402
    _is_in_worktree_checkout,
    _path_yaml_files,
)


def test_is_in_worktree_checkout_accepts_worktrees():
    # Arrange
    parts = (
        "home", "u", "proj", "myrepo", ".worktrees", "feat-x", "config", "PATH.yaml",
    )
    # Act
    result = _is_in_worktree_checkout(parts)
    # Assert
    assert result is True


def test_is_in_worktree_checkout_accepts_claude_worktrees_pair():
    # Arrange
    parts = (
        "home", "u", "proj", "myrepo", ".claude", "worktrees", "agent-1",
        "config", "PATH.yaml",
    )
    # Act
    result = _is_in_worktree_checkout(parts)
    # Assert
    assert result is True


def test_is_in_worktree_checkout_rejects_lone_claude():
    # Arrange — `.claude/` alone (no `worktrees` child) must NOT be
    # skipped so a `.claude/skills/` etc. file is still audited.
    parts = (
        "home", "u", "proj", "myrepo", ".claude", "skills", "config", "PATH.yaml",
    )
    # Act
    result = _is_in_worktree_checkout(parts)
    # Assert
    assert result is False


def test_is_in_worktree_checkout_rejects_canonical_source():
    # Arrange
    parts = ("home", "u", "proj", "myrepo", "config", "PATH.yaml")
    # Act
    result = _is_in_worktree_checkout(parts)
    # Assert
    assert result is False


def test_is_in_worktree_checkout_rejects_substring_lookalike():
    # Arrange — directory literally named ``foo.worktrees`` must not be
    # mistaken for the guarded segment. Skip is component-equality, not
    # substring.
    parts = (
        "home", "u", "proj", "myrepo", "foo.worktrees", "config", "PATH.yaml",
    )
    # Act
    result = _is_in_worktree_checkout(parts)
    # Assert
    assert result is False


def _build_repo_with_canonical_clean_and_stale_worktree(tmp_path):
    """Helper: build a repo whose canonical config/PATH.yaml is CLEAN
    but whose `.worktrees/` and `.claude/worktrees/` siblings carry the
    BUGGY pre-PR-97 fixture.

    This is the lead-specified shape: the SAME violation file under
    `.worktrees/` must NOT cause a fire, but the same file under
    canonical `config/` DOES (the bidirectional pin lives in
    `_DOES_fire_for_violation_under_canonical_config` below)."""
    repo = tmp_path / "myrepo"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "PATH.yaml").write_text(_AFTER_PATH_YAML, encoding="utf-8")
    (repo / ".worktrees" / "stale-branch" / "config").mkdir(parents=True)
    (repo / ".worktrees" / "stale-branch" / "config" / "PATH.yaml").write_text(
        _BEFORE_PATH_YAML, encoding="utf-8"
    )
    (repo / ".claude" / "worktrees" / "agent-stale" / "config").mkdir(parents=True)
    (repo / ".claude" / "worktrees" / "agent-stale" / "config" / "PATH.yaml").write_text(
        _BEFORE_PATH_YAML, encoding="utf-8"
    )
    return repo


def test_path_yaml_files_yields_only_canonical_when_worktrees_present(tmp_path):
    # Arrange
    repo = _build_repo_with_canonical_clean_and_stale_worktree(tmp_path)
    # Act
    yielded = list(_path_yaml_files(repo))
    # Assert
    assert len(yielded) == 1


def test_path_yaml_files_yielded_path_is_canonical_config(tmp_path):
    # Arrange
    repo = _build_repo_with_canonical_clean_and_stale_worktree(tmp_path)
    # Act
    yielded = list(_path_yaml_files(repo))
    # Assert
    assert yielded[0].as_posix().endswith("/myrepo/config/PATH.yaml")


def test_path_yaml_files_DOES_fire_for_violation_under_canonical_config(tmp_path):
    # Arrange — the SAME buggy file as the worktree fixture, but
    # placed at the canonical `<repo>/config/PATH.yaml`. The walker
    # must find it AND the rule check must fire — so the skip above
    # is the worktree guardrail, not a swallow.
    repo = tmp_path / "myrepo-with-canonical-bug"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "PATH.yaml").write_text(_BEFORE_PATH_YAML, encoding="utf-8")
    out: list = []
    # Act
    check_ps_path_001_outer_wrapper(repo, Violation, out)
    # Assert
    assert any(v.rule == "PS-PATH-001" for v in out)
