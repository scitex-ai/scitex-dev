# -*- coding: utf-8 -*-
"""The audit summary must never claim success over live findings.

`audit_project` used to decide its SUCC banner from `visible` — the
severity-FLOOR-filtered finding list — rather than from the findings
themselves. At the default `--severity error`, a tree carrying live W
findings therefore printed output byte-identical to a genuinely clean
tree: `SUCC: <pkg> (<root>): no project-structure violations`, exit 0.

That is a verification-integrity defect, not a cosmetic one. It made a
CLI-driven mutation proof of ANY W-severity rule structurally incapable
of failing: planting the violation changed nothing observable, so the
check said "pass" for a tree it had just found fault with. Reported by
scitex-agent-container on 2026-07-23 against a tree with 53 live PS-220
findings.

The tests below therefore assert on the OUTPUT, not only on the exit
code — a suite that reads exit codes alone cannot see this bug, which is
precisely how it survived. They run the REAL `audit_project` end-to-end
against a temp package tree (no mocks), scoped with `rules={"PS-220"}`
so the counts are driven by one known rule rather than by whatever else
the auditor happens to find.

The exit-code invariant is pinned here too: W findings must keep exiting
0. This fix changes what is REPORTED, never what fails — raising the
exit code would silently re-break every repo the 0.36.0 restage
unblocked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._audit import audit_project

_DIST = "scitex-summary-demo"

_CLEAN_SOURCE = (
    "import scitex_logging as slogging\n"
    "log = slogging.getLogger(__name__)\n"
    "def go():\n    log.success('done')\n"
)
_SOURCE_WITH_BARE_PRINT = "def go():\n    print('hello')\n"

# The per-package opt-in that promotes PS-220 from W to E, so the error
# arm exercises the SAME rule as the warning arm and the only variable
# is the declared severity.
_OPT_IN = (
    "project-type:\n"
    "  - pip\n"
    "audit:\n"
    "  enforce-logging:\n"
    "    level: error\n"
    '    reason: "print migration complete; all sites on scitex-logging"\n'
)
_DEFAULT_CONFIG = "project-type:\n  - pip\n"

_SUCCESS_TEXT = "no project-structure violations"


def _build(repo: Path, body: str, config_yaml: str = _DEFAULT_CONFIG) -> Path:
    """Create a minimal src-layout package whose `_core.py` holds `body`."""
    pkg = repo / "src" / "scitex_summary_demo"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "_core.py").write_text(body, encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        f'[project]\nname = "{_DIST}"\nversion = "0.0.0+local"\n',
        encoding="utf-8",
    )
    cfg = repo / ".scitex" / "dev" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(config_yaml, encoding="utf-8")
    return repo


def _audit(repo: Path, *, json_out: bool = False) -> int:
    return audit_project(_DIST, repo=repo, json_out=json_out, rules={"PS-220"})


def _payload(captured: str) -> dict:
    """Extract the JSON object from captured output that may carry banners."""
    start = captured.index("{")
    end = captured.rindex("}") + 1
    return json.loads(captured[start:end])


@pytest.fixture
def clean_text(tmp_path, capfd) -> str:
    """Human output for a tree with zero PS-220 findings."""
    _build(tmp_path, _CLEAN_SOURCE)
    _audit(tmp_path)
    captured = capfd.readouterr()
    return captured.out + captured.err


@pytest.fixture
def warning_text(tmp_path, capfd) -> str:
    """Human output for a tree with one live W finding (a bare print)."""
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT)
    _audit(tmp_path)
    captured = capfd.readouterr()
    return captured.out + captured.err


@pytest.fixture
def error_text(tmp_path, capfd) -> str:
    """Human output for the same print in a package that opted PS-220 to E."""
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT, config_yaml=_OPT_IN)
    _audit(tmp_path)
    captured = capfd.readouterr()
    return captured.out + captured.err


@pytest.fixture
def clean_payload(tmp_path, capfd) -> dict:
    _build(tmp_path, _CLEAN_SOURCE)
    _audit(tmp_path, json_out=True)
    return _payload(capfd.readouterr().out)


@pytest.fixture
def warning_payload(tmp_path, capfd) -> dict:
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT)
    _audit(tmp_path, json_out=True)
    return _payload(capfd.readouterr().out)


@pytest.fixture
def error_payload(tmp_path, capfd) -> dict:
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT, config_yaml=_OPT_IN)
    _audit(tmp_path, json_out=True)
    return _payload(capfd.readouterr().out)


# --- zero findings: the ONLY state that earns a success banner --------------


def test_zero_findings_print_the_success_banner(clean_text):
    # Arrange — fixture audited a tree on the canonical scitex-logging form
    # Act
    # Assert
    assert _SUCCESS_TEXT in clean_text


def test_zero_findings_exit_zero(tmp_path):
    # Arrange
    _build(tmp_path, _CLEAN_SOURCE)
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


# --- warnings only: NO success banner, count shown, exit still 0 ------------


def test_warning_findings_suppress_the_success_banner(warning_text):
    # Arrange — one bare print: a live W finding, below the default floor
    # Act
    # Assert — this is the exact claim the old code got wrong
    assert _SUCCESS_TEXT not in warning_text


def test_warning_findings_report_both_counts_in_human_output(warning_text):
    # Arrange
    # Act
    # Assert
    assert "0 error(s), 1 warning(s)" in warning_text


def test_below_floor_findings_name_how_to_list_them(warning_text):
    # Arrange — a count with no route to the detail would be a half-fix
    # Act
    # Assert
    assert "--severity warning" in warning_text


def test_warning_findings_still_exit_zero(tmp_path):
    # Arrange — the invariant the fix must NOT disturb: W never blocks
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT)
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


# --- errors: reported and blocking, exactly as before -----------------------


def test_error_findings_report_both_counts_in_human_output(error_text):
    # Arrange — identical source; the opt-in promotes PS-220 W -> E
    # Act
    # Assert
    assert "1 error(s), 0 warning(s)" in error_text


def test_error_findings_suppress_the_success_banner(error_text):
    # Arrange
    # Act
    # Assert
    assert _SUCCESS_TEXT not in error_text


def test_error_findings_exit_nonzero(tmp_path):
    # Arrange
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT, config_yaml=_OPT_IN)
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 1


# --- --json carries BOTH counts ---------------------------------------------


def test_json_reports_the_warning_count_for_a_warning_only_tree(warning_payload):
    # Arrange — a consumer reading only `errors` inherits the same blind spot
    # Act
    # Assert
    assert warning_payload["warnings"] == 1


def test_json_reports_no_errors_for_a_warning_only_tree(warning_payload):
    # Arrange
    # Act
    # Assert
    assert warning_payload["errors"] == 0


def test_json_exit_code_is_zero_for_a_warning_only_tree(warning_payload):
    # Arrange
    # Act
    # Assert
    assert warning_payload["exit_code"] == 0


def test_json_reports_zero_warnings_for_a_clean_tree(clean_payload):
    # Arrange
    # Act
    # Assert
    assert clean_payload["warnings"] == 0


def test_json_reports_the_error_count_for_an_opted_in_package(error_payload):
    # Arrange
    # Act
    # Assert
    assert error_payload["errors"] == 1


def test_json_exit_code_is_one_for_an_opted_in_package(error_payload):
    # Arrange
    # Act
    # Assert
    assert error_payload["exit_code"] == 1


# --- the mutation the old summary could not see -----------------------------


def _warning_counts_before_and_after_planting_a_print(tmp_path, capfd):
    """Audit the SAME tree twice, mutating only the one source line."""
    _build(tmp_path, _CLEAN_SOURCE)
    _audit(tmp_path, json_out=True)
    before = _payload(capfd.readouterr().out)
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT)
    _audit(tmp_path, json_out=True)
    after = _payload(capfd.readouterr().out)
    return before["warnings"], after["warnings"]


def test_a_tree_without_a_bare_print_reports_no_warnings(tmp_path, capfd):
    # Arrange — the control arm of the mutation proof
    counts = _warning_counts_before_and_after_planting_a_print
    # Act
    before, _after = counts(tmp_path, capfd)
    # Assert
    assert before == 0


def test_planting_a_bare_print_increments_the_reported_warning_count(tmp_path, capfd):
    # Arrange — pre-fix BOTH runs emitted the identical success banner,
    # which is why a CLI-driven mutation proof of a W rule could not fail.
    counts = _warning_counts_before_and_after_planting_a_print
    # Act
    _before, after = counts(tmp_path, capfd)
    # Assert
    assert after == 1


# EOF
