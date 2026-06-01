"""Tests for PS-CLEW-001 / PS-AGENT-001 — Clew claims invariants.

Covers both rules in isolation and exercises the historical cross-check
suggested by the operator directive 2026-06-01:

  * paper-scitex-clew commit 87a0f7b — post-self-verify version of
    `scripts/cohorts/_shared/prompts/examples/cohort_a_capsule_01_minimal/
    scripts/agent/03_register_claims.py` — must NOT flag.
  * A minimal pre-self-verify reproducer (add_claim only, no
    verify_claim / list_claims) — must flag.

We do NOT git-checkout the historical commit (per directive); we
extract the file content from the local git history via
``git show <sha>:<path>`` if available, otherwise fall back to a
hand-written equivalent fixture. The test is parameterised so it
runs against whichever it can find.

No mocks (NM001-003) — real temp repos.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._audit import Violation
from scitex_dev._cli.audit._project._check_clew_claims import (
    check_ps_agent_001_agent_script_no_claims_json,
    check_ps_clew_001_add_claim_without_self_verify,
)


# ── Hand-written fixtures (no-mocks fallback) ───────────────────────────

# Pre-self-verify shape: add_claim called in a loop, no verify_claim / list_claims.
# This IS the failure mode the rule targets.
_PRE_SELF_VERIFY = '''
"""Stage 03 — pre-self-verify shape (the buggy pattern)."""
from __future__ import annotations

import json
from pathlib import Path

import scitex as stx
import scitex_clew as clew


@stx.session
def main(CONFIG=stx.session.INJECTED, logger=stx.session.INJECTED):
    claims_json = Path(eval(CONFIG.PATH.CLAIMS_JSON)).resolve()
    output_txt = Path(eval(CONFIG.PATH.OUTPUT_TXT)).resolve()
    claims_payload = {"capsule_id": "x", "claims": [{"q": "?", "a": 1}]}
    claims_json.parent.mkdir(parents=True, exist_ok=True)
    claims_json.write_text(json.dumps(claims_payload, indent=2))
    for ans in claims_payload["claims"]:
        c = clew.add_claim(
            file_path=str(claims_json),
            claim_type="value",
            line_number=1,
            claim_value=str(ans["a"]),
            source_file=str(output_txt),
        )
        logger.info(f"claim {c.claim_id}")
    return 0


if __name__ == "__main__":
    main()
'''

# Post-self-verify shape: add_claim + verify_claim + list_claims.
_POST_SELF_VERIFY = '''
"""Stage 03 — post-self-verify shape (commit 87a0f7b)."""
from __future__ import annotations

import json
from pathlib import Path

import scitex as stx
import scitex_clew as clew


@stx.session
def main(CONFIG=stx.session.INJECTED, logger=stx.session.INJECTED):
    claims_json = Path(eval(CONFIG.PATH.CLAIMS_JSON)).resolve()
    output_txt = Path(eval(CONFIG.PATH.OUTPUT_TXT)).resolve()
    claims_payload = {"capsule_id": "x", "claims": [{"q": "?", "a": 1}]}
    claims_json.parent.mkdir(parents=True, exist_ok=True)
    claims_json.write_text(json.dumps(claims_payload, indent=2))
    registered = []
    for ans in claims_payload["claims"]:
        c = clew.add_claim(
            file_path=str(claims_json),
            claim_type="value",
            line_number=1,
            claim_value=str(ans["a"]),
            source_file=str(output_txt),
        )
        registered.append(c)
    listed = clew.list_claims(file_path=str(claims_json))
    assert len(listed) == len(registered)
    for c in registered:
        result = clew.verify_claim(c.claim_id)
        assert result.get("source_verified") is True
    return 0


if __name__ == "__main__":
    main()
'''


PAPER_REPO = Path("/home/ywatanabe/proj/paper-scitex-clew")
HISTORICAL_PATH = (
    "scripts/cohorts/_shared/prompts/examples/cohort_a_capsule_01_minimal/"
    "scripts/agent/03_register_claims.py"
)


def _git_show(repo: Path, rev: str, path: str) -> str | None:
    """Extract historical file content via `git show <sha>:<path>`.

    Returns None if the repo / rev / path is unavailable (test
    falls back to the hand-written fixture).
    """
    git = shutil.which("git")
    if not git or not (repo / ".git").exists():
        return None
    try:
        result = subprocess.run(
            [git, "-C", str(repo), "show", f"{rev}:{path}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def _write_agent_script(repo: Path, content: str, name: str = "03_register_claims.py") -> Path:
    target_dir = repo / "scripts" / "agent"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / name
    target.write_text(content)
    return target


def _historical_content_or_skip(rev: str) -> str:
    """Fixture helper: return historical PATH content or skip the test.

    Centralises the skip so per-test bodies stay single-assertion
    (PA-307 §3 / TQ007 compliance).
    """
    content = _git_show(PAPER_REPO, rev, HISTORICAL_PATH)
    if content is None:
        pytest.skip(
            f"paper-scitex-clew historical content unavailable for {rev} — "
            "synthetic equivalent tests cover this case."
        )
    return content


@pytest.fixture
def historical_post_fix_content() -> str:
    """commit 87a0f7b — post-self-verify shape from paper-scitex-clew."""
    return _historical_content_or_skip("87a0f7b")


@pytest.fixture
def historical_635799a_content() -> str:
    """commit 635799a — list_claims branch (no verify_claim)."""
    return _historical_content_or_skip("635799a")


def _run_ps_clew_001(repo: Path) -> set[str]:
    out: list = []
    check_ps_clew_001_add_claim_without_self_verify(repo, Violation, out)
    return {v.rule for v in out}


def _run_ps_agent_001(repo: Path) -> list:
    out: list = []
    check_ps_agent_001_agent_script_no_claims_json(repo, Violation, out)
    return out


# ── PS-CLEW-001 ─────────────────────────────────────────────────────────


def test_ps_clew_001_fires_on_pre_self_verify_synthetic(tmp_path):
    # Arrange
    _write_agent_script(tmp_path, _PRE_SELF_VERIFY)
    # Act
    out: list = []
    check_ps_clew_001_add_claim_without_self_verify(tmp_path, Violation, out)
    # Assert
    codes = {v.rule for v in out}
    assert "PS-CLEW-001" in codes


def test_ps_clew_001_does_not_fire_on_post_self_verify_synthetic(tmp_path):
    # Arrange
    _write_agent_script(tmp_path, _POST_SELF_VERIFY)
    # Act
    out: list = []
    check_ps_clew_001_add_claim_without_self_verify(tmp_path, Violation, out)
    # Assert
    codes = {v.rule for v in out}
    assert "PS-CLEW-001" not in codes


def test_ps_clew_001_does_not_fire_on_historical_post_fix(
    tmp_path, historical_post_fix_content
):
    """Cross-check: the canonical post-fix version (commit 87a0f7b in
    paper-scitex-clew) must NOT flag PS-CLEW-001.

    The skip-on-missing-fixture decision lives in
    `historical_post_fix_content` so the body stays single-assertion.
    """
    # Arrange
    _write_agent_script(tmp_path, historical_post_fix_content)
    # Act
    codes = _run_ps_clew_001(tmp_path)
    # Assert
    assert "PS-CLEW-001" not in codes


def test_ps_clew_001_does_not_fire_on_historical_635799a(
    tmp_path, historical_635799a_content
):
    """Cross-check: commit 635799a calls list_claims() (no
    verify_claim). Per the spec, list_claims is one of the two
    accepted self-verify forms, so the rule does NOT flag.

    Documents the finding: 635799a is not actually a positive-case
    fixture for PS-CLEW-001 — even though it predates the in-process
    validity gate, it satisfies the list_claims branch of the rule.
    The skip lives in the fixture for TQ007 compliance.
    """
    # Arrange
    _write_agent_script(tmp_path, historical_635799a_content)
    # Act
    codes = _run_ps_clew_001(tmp_path)
    # Assert
    assert "PS-CLEW-001" not in codes


def test_ps_clew_001_handles_scitex_clew_module_form(tmp_path):
    # Arrange — `scitex_clew.add_claim` form (no `clew` alias).
    src = '''
import scitex_clew

def f():
    scitex_clew.add_claim(file_path="x", claim_type="value", line_number=1,
                          claim_value="1", source_file="y")
'''
    (tmp_path / "mod.py").write_text(src)
    # Act
    out: list = []
    check_ps_clew_001_add_claim_without_self_verify(tmp_path, Violation, out)
    # Assert
    assert "PS-CLEW-001" in {v.rule for v in out}


def test_ps_clew_001_handles_from_import_form(tmp_path):
    # Arrange — `from scitex_clew import add_claim` lifts the name.
    src = '''
from scitex_clew import add_claim, list_claims

def f():
    c = add_claim(file_path="x", claim_type="value", line_number=1,
                  claim_value="1", source_file="y")
    listed = list_claims(file_path="x")
'''
    (tmp_path / "mod.py").write_text(src)
    # Act
    out: list = []
    check_ps_clew_001_add_claim_without_self_verify(tmp_path, Violation, out)
    # Assert — list_claims is present, so PS-CLEW-001 does not fire.
    assert "PS-CLEW-001" not in {v.rule for v in out}


def test_ps_clew_001_silent_when_add_claim_absent(tmp_path):
    # Arrange — module unrelated to clew.
    (tmp_path / "mod.py").write_text("def foo():\n    return 42\n")
    # Act
    out: list = []
    check_ps_clew_001_add_claim_without_self_verify(tmp_path, Violation, out)
    # Assert
    assert out == []


# ── PS-AGENT-001 ─────────────────────────────────────────────────────────


def test_ps_agent_001_fires_when_add_claim_but_no_claims_json_write(tmp_path):
    # Arrange — agent script calls add_claim but writes nothing.
    src = '''
import scitex_clew as clew

def main():
    for i in range(3):
        c = clew.add_claim(file_path="x", claim_type="value", line_number=i,
                           claim_value=str(i), source_file="y")
        clew.verify_claim(c.claim_id)
'''
    _write_agent_script(tmp_path, src)
    # Act
    out: list = []
    check_ps_agent_001_agent_script_no_claims_json(tmp_path, Violation, out)
    # Assert
    assert "PS-AGENT-001" in {v.rule for v in out}


def test_ps_agent_001_does_not_fire_when_path_write_text_claims_json(tmp_path):
    # Arrange — agent script writes claims.json via Path.write_text.
    src = '''
import json
from pathlib import Path
import scitex_clew as clew

def main():
    claims_json = Path("data/results/claims.json")
    claims_json.parent.mkdir(parents=True, exist_ok=True)
    claims_json.write_text(json.dumps({"x": 1}))
    clew.add_claim(file_path=str(claims_json), claim_type="value",
                   line_number=1, claim_value="1", source_file="y")
'''
    _write_agent_script(tmp_path, src)
    # Act
    out: list = []
    check_ps_agent_001_agent_script_no_claims_json(tmp_path, Violation, out)
    # Assert
    assert "PS-AGENT-001" not in {v.rule for v in out}


def test_ps_agent_001_does_not_fire_when_stx_io_save_claims_json(tmp_path):
    # Arrange — terminus written via stx.io.save with claims.json literal.
    src = '''
import scitex as stx
import scitex_clew as clew

def main():
    stx.io.save({"x": 1}, "data/results/claims.json")
    clew.add_claim(file_path="data/results/claims.json", claim_type="value",
                   line_number=1, claim_value="1", source_file="y")
'''
    _write_agent_script(tmp_path, src)
    # Act
    out: list = []
    check_ps_agent_001_agent_script_no_claims_json(tmp_path, Violation, out)
    # Assert
    assert "PS-AGENT-001" not in {v.rule for v in out}


def test_ps_agent_001_does_not_fire_on_historical_post_fix(
    tmp_path, historical_post_fix_content
):
    """Cross-check: paper-scitex-clew commit 87a0f7b writes
    claims.json via `claims_json.write_text(...)` where the receiver
    binds to a Path derived from CONFIG.PATH.CLAIMS_JSON. Must NOT
    flag PS-AGENT-001. The skip lives in the fixture (TQ007 compliance).
    """
    # Arrange
    _write_agent_script(tmp_path, historical_post_fix_content)
    # Act
    out = _run_ps_agent_001(tmp_path)
    # Assert
    assert "PS-AGENT-001" not in {v.rule for v in out}


def test_ps_agent_001_scope_excludes_non_agent_scripts(tmp_path):
    # Arrange — same buggy shape but NOT under scripts/agent/.
    src = '''
import scitex_clew as clew
def f():
    clew.add_claim(file_path="x", claim_type="value", line_number=1,
                   claim_value="1", source_file="y")
    clew.verify_claim("abc")
'''
    (tmp_path / "scripts" / "analysis").mkdir(parents=True)
    (tmp_path / "scripts" / "analysis" / "01_x.py").write_text(src)
    # Act
    out: list = []
    check_ps_agent_001_agent_script_no_claims_json(tmp_path, Violation, out)
    # Assert — out of scope.
    assert "PS-AGENT-001" not in {v.rule for v in out}


def test_ps_agent_001_silent_when_no_add_claim(tmp_path):
    # Arrange — agent script with no add_claim call.
    _write_agent_script(tmp_path, "x = 1\n")
    # Act
    out: list = []
    check_ps_agent_001_agent_script_no_claims_json(tmp_path, Violation, out)
    # Assert
    assert out == []


# ── audit_project integration ────────────────────────────────────────────


def _build_buggy_research_repo(repo: Path) -> None:
    """Arrange helper: minimal research repo with a buggy agent script."""
    from scitex_dev._cli.audit._config import write_config

    (repo / ".scitex/dev").mkdir(parents=True)
    write_config(repo, project_types=["research"])
    src = '''
import scitex_clew as clew
def main():
    for i in range(3):
        clew.add_claim(file_path="x", claim_type="value", line_number=i,
                       claim_value=str(i), source_file="y")
'''
    _write_agent_script(repo, src)
    (repo / "scripts" / "analysis").mkdir(parents=True)
    (repo / "scripts" / "analysis" / "01_x.py").write_text("x = 1\n")
    (repo / "tests" / "scripts" / "agent").mkdir(parents=True)
    (repo / "tests" / "scripts" / "agent" / "test_03_register_claims.py").write_text(
        "def test_x():\n    assert True\n"
    )
    (repo / "tests" / "scripts" / "analysis").mkdir(parents=True)
    (repo / "tests" / "scripts" / "analysis" / "test_01_x.py").write_text(
        "def test_x():\n    assert True\n"
    )


def _run_audit_project_json(repo: Path) -> dict:
    """Act helper: run audit_project --json against ``repo`` and return payload."""
    import io
    import json
    from contextlib import redirect_stdout

    from scitex_dev._cli.audit._project._audit import audit_project

    buf = io.StringIO()
    with redirect_stdout(buf):
        audit_project("demo-research", repo=repo, json_out=True, severity="warning")
    return json.loads(buf.getvalue())


@pytest.fixture
def audit_project_payload_buggy_research(tmp_path):
    """Shared Arrange+Act: buggy research repo audit payload."""
    _build_buggy_research_repo(tmp_path)
    return _run_audit_project_json(tmp_path)


def test_audit_project_emits_ps_clew_001_in_json(audit_project_payload_buggy_research):
    # Arrange (shared via fixture)
    payload = audit_project_payload_buggy_research
    # Act
    by_rule = {v["rule"] for v in payload["violations"]}
    # Assert
    assert "PS-CLEW-001" in by_rule


def test_audit_project_emits_ps_agent_001_in_json(audit_project_payload_buggy_research):
    # Arrange (shared via fixture)
    payload = audit_project_payload_buggy_research
    # Act
    by_rule = {v["rule"] for v in payload["violations"]}
    # Assert
    assert "PS-AGENT-001" in by_rule


def test_audit_project_records_ps_clew_001_severity_w(audit_project_payload_buggy_research):
    # Arrange (shared via fixture)
    payload = audit_project_payload_buggy_research
    # Act
    by_rule_record = {v["rule"]: v for v in payload["violations"]}
    # Assert — PS-CLEW-001 is a warning.
    assert by_rule_record["PS-CLEW-001"]["severity"] == "W"


def test_audit_project_records_ps_agent_001_severity_e(audit_project_payload_buggy_research):
    # Arrange (shared via fixture)
    payload = audit_project_payload_buggy_research
    # Act
    by_rule_record = {v["rule"]: v for v in payload["violations"]}
    # Assert — PS-AGENT-001 is an error.
    assert by_rule_record["PS-AGENT-001"]["severity"] == "E"
