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

The tests below therefore assert on the REPORT, not only on the exit
code — a suite that reads exit codes alone cannot see this bug, which is
precisely how it survived. They run the REAL `audit_project` end-to-end
against a temp package tree (no mocks), scoped with `rules={"PS-220"}`
so the counts are driven by one known rule rather than by whatever else
the auditor happens to find.

WHICH TRANSPORT THE BANNER USES, and why these tests read the log rather
than a stream. Measured, not assumed: `_emit` calls
`scitex_logging.getLogger("scitex_dev.audit")`, and that logger carries
NO handlers of its own with `propagate=True`. The banner therefore
reaches a terminal only by propagating to whatever handlers
scitex-logging installed on the ROOT logger (a lazy stderr handler and a
rotating file handler). That root configuration is ambient: it depends
on import order and on whatever else has touched logging in the same
process. A first version of this file captured stderr+stdout with
`capfd`; it passed in a bare shell and failed all four banner assertions
under the full CI suite, which received the click-printed epilogue and
none of the logged banner.

So the assertions below target the logging transport directly, via
`caplog`. That is deterministic across environments AND strictly
stronger than the stream version: it additionally pins the LEVEL each
line is emitted at (`SUCC` / `WARN` / `ERRO`), so a regression that
downgraded the summary to `info` — invisible in real use, since the
audit logger's default level is WARNING — now fails a test. The `--json`
assertions still read stdout, because that payload genuinely goes
through `click.echo`; those passed in CI unchanged.

The exit-code invariant is pinned here too: W findings must keep exiting
0. This fix changes what is REPORTED, never what fails — raising the
exit code would silently re-break every repo the 0.36.0 restage
unblocked.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

# Imported for its SIDE EFFECT as much as its name: `_emit` binds its module
# level `_logger` via `scitex_logging.getLogger("scitex_dev.audit")`, and
# scitex-logging can only return a `SciTeXLogger` (the class carrying
# `.success`) if NOTHING has already created that logger name through the
# stdlib — `logging.getLogger` caches by name and hands back the plain
# `Logger` forever after. `_audit.py` imports `_emit` lazily, INSIDE
# `audit_project`, so that window is wide. Importing here closes it for this
# module, and the fixtures below deliberately never pass `logger=` to
# `caplog.set_level`, which would create the plain logger and break the
# binding. See the note in the PR: the same ordering hazard is a latent
# crash in production, tracked separately.
from scitex_dev._cli.audit import _emit as _emit_module  # noqa: F401
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


_AUDIT_LOGGER = "scitex_dev.audit"


def _audit_and_capture_log(repo: Path, caplog) -> list[tuple[str, str]]:
    """Audit `repo` and return the banner as (levelname, message) pairs.

    Reads the logging transport `_emit` actually uses (see the module
    docstring), so the result does not depend on which handlers happen to
    be attached to the root logger in this environment.
    """
    # Root only — naming the audit logger here would create it through the
    # stdlib and strip `.success` off `_emit._logger` (see the module header).
    # Root is enough: the audit logger has no level of its own and
    # propagates, so its records reach caplog's root handler regardless.
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    _audit(repo)
    return [
        (record.levelname, record.getMessage())
        for record in caplog.records
        if record.name == _AUDIT_LOGGER
    ]


def _messages(lines: list[tuple[str, str]]) -> str:
    return "\n".join(message for _level, message in lines)


@pytest.fixture
def clean_lines(tmp_path, caplog) -> list[tuple[str, str]]:
    """Banner lines for a tree with zero PS-220 findings."""
    _build(tmp_path, _CLEAN_SOURCE)
    return _audit_and_capture_log(tmp_path, caplog)


@pytest.fixture
def warning_lines(tmp_path, caplog) -> list[tuple[str, str]]:
    """Banner lines for a tree with one live W finding (a bare print)."""
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT)
    return _audit_and_capture_log(tmp_path, caplog)


@pytest.fixture
def error_lines(tmp_path, caplog) -> list[tuple[str, str]]:
    """Banner lines for the same print in a package that opted PS-220 to E."""
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT, config_yaml=_OPT_IN)
    return _audit_and_capture_log(tmp_path, caplog)


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


def test_zero_findings_log_the_success_banner(clean_lines):
    # Arrange — fixture audited a tree on the canonical scitex-logging form
    # Act
    # Assert
    assert _SUCCESS_TEXT in _messages(clean_lines)


def test_zero_findings_log_the_success_banner_at_succ_level(clean_lines):
    # Arrange — the level is what makes the banner visible; pin it too
    # Act
    levels = [lvl for lvl, msg in clean_lines if _SUCCESS_TEXT in msg]
    # Assert
    assert levels == ["SUCC"]


def test_zero_findings_exit_zero(tmp_path):
    # Arrange
    _build(tmp_path, _CLEAN_SOURCE)
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


# --- warnings only: NO success banner, count shown, exit still 0 ------------


def test_warning_findings_suppress_the_success_banner(warning_lines):
    # Arrange — one bare print: a live W finding, below the default floor
    # Act
    # Assert — this is the exact claim the old code got wrong
    assert _SUCCESS_TEXT not in _messages(warning_lines)


def test_warning_findings_report_both_counts_in_the_banner(warning_lines):
    # Arrange
    # Act
    # Assert
    assert "0 error(s), 1 warning(s)" in _messages(warning_lines)


def test_warning_findings_log_their_headline_at_warn_level(warning_lines):
    # Arrange — a summary downgraded to info would be invisible in real use
    # Act
    levels = [lvl for lvl, msg in warning_lines if "0 error(s), 1 warning(s)" in msg]
    # Assert
    assert levels == ["WARN"]


def test_below_floor_findings_name_how_to_list_them(warning_lines):
    # Arrange — a count with no route to the detail would be a half-fix
    # Act
    # Assert
    assert "--severity warning" in _messages(warning_lines)


def test_warning_findings_still_exit_zero(tmp_path):
    # Arrange — the invariant the fix must NOT disturb: W never blocks
    _build(tmp_path, _SOURCE_WITH_BARE_PRINT)
    # Act
    code = _audit(tmp_path)
    # Assert
    assert code == 0


# --- errors: reported and blocking, exactly as before -----------------------


def test_error_findings_report_both_counts_in_the_banner(error_lines):
    # Arrange — identical source; the opt-in promotes PS-220 W -> E
    # Act
    # Assert
    assert "1 error(s), 0 warning(s)" in _messages(error_lines)


def test_error_findings_log_their_headline_at_erro_level(error_lines):
    # Arrange
    # Act
    levels = [lvl for lvl, msg in error_lines if "1 error(s), 0 warning(s)" in msg]
    # Assert
    assert levels == ["ERRO"]


def test_error_findings_suppress_the_success_banner(error_lines):
    # Arrange
    # Act
    # Assert
    assert _SUCCESS_TEXT not in _messages(error_lines)


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
