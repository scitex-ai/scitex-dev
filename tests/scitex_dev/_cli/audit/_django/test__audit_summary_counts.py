# -*- coding: utf-8 -*-
"""`audit_django` must never claim success over live findings.

The sibling of the defect PR #417 fixed in `audit_project`, confirmed to
reproduce here before being fixed. `audit_django` decided its SUCC
banner from `visible` — the severity-FLOOR-filtered finding list —
rather than from the findings themselves. At the default
`--severity error`, a tree carrying live W findings printed output
byte-identical to a genuinely clean tree:

    SUCC: <pkg>: no Django-standard violations          exit 0

Measured pre-fix on the fixtures below, scoped to `rules={"DJ-107"}`:
the dirty tree and the clean tree produced identical banner lines, and
`--json` reported `"violations": []` with no warning count at all. So a
CLI-driven mutation proof of ANY W-severity DJ rule was structurally
incapable of failing — planting the violation changed nothing
observable.

These tests therefore assert on the REPORT, not only on the exit code.
A suite reading exit codes alone cannot see this bug: the exit code was
correct throughout and only the banner lied.

TRANSPORT — why these read `caplog` and not a stream. Measured, not
assumed (see the PR #417 module docstring for the full account):
`_emit` logs through `scitex_logging.getLogger("scitex_dev.audit")`,
which carries NO handlers of its own and propagates. The banner reaches
a terminal only via handlers on the ROOT logger — ambient state that
depends on import order. `capfd` on `.out + .err` did NOT capture it
under the full CI suite. Reading the log is deterministic AND strictly
stronger: it pins the LEVEL of each line, so a regression downgrading
the summary to `info` (invisible in real use — the audit logger's
default level is WARNING) fails a test. The `--json` assertions read
stdout, because that payload genuinely goes through `click.echo`.

DIFFERENCE FROM THE PROJECT AUDITOR'S SUITE: `audit_project` could
exercise its error arm on the SAME rule as its warning arm, because
PS-220 has a per-package opt-in that promotes it W -> E. The DJ rules
carry fixed severities with no such toggle, so the error arm here uses
DJ-101 (E) while the warning arm uses DJ-107 (W). Each arm is still
scoped to exactly one rule, so the counts are driven by a known finding
rather than by whatever else the auditor happens to trip over.

The exit-code invariant is pinned on both the human and `--json` paths:
W findings must keep exiting 0 and E findings must keep exiting 1. This
fix changes what is REPORTED, never what fails.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

# Imported for its SIDE EFFECT as much as its name: `_emit` binds its
# module-level `_logger` via `scitex_logging.getLogger("scitex_dev.audit")`,
# and scitex-logging can only return a `SciTeXLogger` (the class carrying
# `.success`) if NOTHING has already created that logger name through the
# stdlib — `logging.getLogger` caches by name and hands back the plain
# `Logger` forever after. `_audit.py` imports `_emit` lazily, INSIDE
# `audit_django`, so that window is wide. Importing here closes it for this
# module, and the fixtures below deliberately never pass `logger=` to
# `caplog.set_level`, which would create the plain logger and break the
# binding. The same ordering hazard is a latent crash in production,
# tracked separately as `audit-emit-logger-ordering-crash`.
from scitex_dev._cli.audit import _emit as _emit_module  # noqa: F401
from scitex_dev._cli.audit._django._audit import audit_django

_DIST = "scitex-django-summary-demo"
_SUCCESS_TEXT = "no Django-standard violations"
_AUDIT_LOGGER = "scitex_dev.audit"

_MANAGE_PY = (
    "import os\n"
    'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n'
)


def _build(repo: Path, *, server_entrypoints: bool = True) -> Path:
    """A Django tree. Omitting asgi/wsgi is the single DJ-107 (W) finding."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "manage.py").write_text(_MANAGE_PY, encoding="utf-8")
    config = repo / "config"
    config.mkdir(exist_ok=True)
    (config / "__init__.py").write_text("", encoding="utf-8")
    (config / "urls.py").write_text("urlpatterns = []\n", encoding="utf-8")
    settings = config / "settings"
    settings.mkdir(exist_ok=True)
    (settings / "__init__.py").write_text(
        "from .settings_dev import *\n", encoding="utf-8"
    )
    for name in ("settings_shared", "settings_dev", "settings_prod"):
        (settings / f"{name}.py").write_text("", encoding="utf-8")
    if server_entrypoints:
        for name in ("asgi", "wsgi"):
            (config / f"{name}.py").write_text("", encoding="utf-8")
    return repo


def _build_error_tree(repo: Path) -> Path:
    """A Django app with no `config/` at all — the single DJ-101 (E) finding."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "manage.py").write_text(_MANAGE_PY, encoding="utf-8")
    return repo


def _audit(repo: Path, *, rules: set[str], json_out: bool = False) -> int:
    return audit_django(_DIST, repo=repo, json_out=json_out, rules=rules)


def _payload(captured: str) -> dict:
    """Extract the JSON object from output that may carry banners."""
    start = captured.index("{")
    end = captured.rindex("}") + 1
    return json.loads(captured[start:end])


def _audit_and_capture_log(repo: Path, caplog, *, rules: set[str]):
    """Audit `repo` and return the banner as (levelname, message) pairs.

    Reads the logging transport `_emit` actually uses, so the result does
    not depend on which handlers happen to be attached to the root logger.
    """
    # Root only — naming the audit logger here would create it through the
    # stdlib and strip `.success` off `_emit._logger` (see the module header).
    caplog.set_level(logging.DEBUG)
    caplog.clear()
    _audit(repo, rules=rules)
    return [
        (record.levelname, record.getMessage())
        for record in caplog.records
        if record.name == _AUDIT_LOGGER
    ]


def _messages(lines) -> str:
    return "\n".join(message for _level, message in lines)


# Each fixture builds into its OWN subdirectory of tmp_path. Sharing
# tmp_path would silently defeat the mutation control below: `_build`
# only ADDS files, so building "dirty" over an existing "clean" tree
# leaves asgi/wsgi in place and both trees come out clean — the two
# halves then compare equal for a reason that has nothing to do with the
# banner. Caught by that test failing on the first run.
@pytest.fixture
def clean_lines(tmp_path, caplog):
    """Banner lines for a tree with zero DJ-107 findings."""
    repo = _build(tmp_path / "clean", server_entrypoints=True)
    return _audit_and_capture_log(repo, caplog, rules={"DJ-107"})


@pytest.fixture
def warning_lines(tmp_path, caplog):
    """Banner lines for a tree with one live W finding (missing asgi/wsgi)."""
    repo = _build(tmp_path / "dirty", server_entrypoints=False)
    return _audit_and_capture_log(repo, caplog, rules={"DJ-107"})


@pytest.fixture
def error_lines(tmp_path, caplog):
    """Banner lines for a tree with one live E finding (no `config/`)."""
    repo = _build_error_tree(tmp_path / "err")
    return _audit_and_capture_log(repo, caplog, rules={"DJ-101"})


@pytest.fixture
def clean_payload(tmp_path, capfd) -> dict:
    _build(tmp_path, server_entrypoints=True)
    _audit(tmp_path, rules={"DJ-107"}, json_out=True)
    return _payload(capfd.readouterr().out)


@pytest.fixture
def warning_payload(tmp_path, capfd) -> dict:
    _build(tmp_path, server_entrypoints=False)
    _audit(tmp_path, rules={"DJ-107"}, json_out=True)
    return _payload(capfd.readouterr().out)


@pytest.fixture
def error_payload(tmp_path, capfd) -> dict:
    _build_error_tree(tmp_path)
    _audit(tmp_path, rules={"DJ-101"}, json_out=True)
    return _payload(capfd.readouterr().out)


# --- zero findings: the ONLY state that earns a success banner --------------


def test_zero_findings_log_the_success_banner(clean_lines):
    # Arrange — fixture audited a tree with both server entry points
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
    _build(tmp_path, server_entrypoints=True)
    # Act
    code = _audit(tmp_path, rules={"DJ-107"})
    # Assert
    assert code == 0


# --- live warnings at the default floor: SUCC must be SUPPRESSED ------------


def test_live_warning_suppresses_the_success_banner(warning_lines):
    # Arrange — one live DJ-107 finding, audited at the default `error` floor
    # Act
    # Assert — this is the whole defect: pre-fix this banner was printed
    assert _SUCCESS_TEXT not in _messages(warning_lines)


def test_live_warning_reports_the_warning_count(warning_lines):
    # Arrange
    # Act
    # Assert — the count must survive the floor filter that hides the detail
    assert "0 error(s), 1 warning(s)" in _messages(warning_lines)


def test_live_warning_headline_is_emitted_at_warn_level(warning_lines):
    # Arrange — an `info` downgrade would be invisible in real use
    # Act
    levels = [lvl for lvl, msg in warning_lines if "warning(s)" in msg]
    # Assert — scitex-logging's own level name, as #417 pins "SUCC"
    assert levels and set(levels) == {"WARN"}


def test_live_warning_names_how_to_list_below_floor_findings(warning_lines):
    # Arrange — a count with no route to the detail would be a half-fix
    # Act
    # Assert
    assert "re-run with `--severity warning`" in _messages(warning_lines)


def test_live_warning_still_exits_zero(tmp_path):
    # Arrange — INVARIANT: warnings report, they do not block
    _build(tmp_path, server_entrypoints=False)
    # Act
    code = _audit(tmp_path, rules={"DJ-107"})
    # Assert
    assert code == 0


def test_live_warning_output_differs_from_a_clean_tree(tmp_path, clean_lines, warning_lines):
    # Arrange — the mutation control: pre-fix these two were identical.
    # The two trees live in different subdirectories, and the banner names
    # the tree it graded, so the raw messages differ by PATH alone. Erase
    # the path first: otherwise this passes without the fix and proves
    # nothing about the banner.
    clean = _messages(clean_lines).replace(str(tmp_path / "clean"), "<ROOT>")
    warned = _messages(warning_lines).replace(str(tmp_path / "dirty"), "<ROOT>")
    # Act
    # Assert
    assert clean != warned


# --- errors: unchanged, still blocking --------------------------------------


def test_error_finding_is_reported(error_lines):
    # Arrange — one live DJ-101 finding
    # Act
    # Assert
    assert "1 error(s)" in _messages(error_lines)


def test_error_finding_headline_is_emitted_at_error_level(error_lines):
    # Arrange
    # Act
    levels = [lvl for lvl, msg in error_lines if "error(s)" in msg]
    # Assert — scitex-logging's own level name, as #417 pins "SUCC"
    assert levels and set(levels) == {"ERRO"}


def test_error_finding_suppresses_the_success_banner(error_lines):
    # Arrange
    # Act
    # Assert
    assert _SUCCESS_TEXT not in _messages(error_lines)


def test_error_finding_exits_one(tmp_path):
    # Arrange — INVARIANT: E findings still block, exactly as before
    _build_error_tree(tmp_path)
    # Act
    code = _audit(tmp_path, rules={"DJ-101"})
    # Assert
    assert code == 1


# --- the --json path carries the same counts --------------------------------


def test_json_clean_tree_reports_zero_warnings(clean_payload):
    # Arrange
    # Act
    # Assert
    assert clean_payload["errors"] == 0 and clean_payload["warnings"] == 0


def test_json_exposes_the_warning_count(warning_payload):
    # Arrange — a consumer reading only `errors` inherited the same blind spot
    # Act
    # Assert
    assert warning_payload["warnings"] == 1


def test_json_warning_only_exit_code_stays_zero(warning_payload):
    # Arrange — INVARIANT, asserted on the machine path too
    # Act
    # Assert
    assert warning_payload["exit_code"] == 0 and warning_payload["errors"] == 0


def test_json_error_exit_code_stays_one(error_payload):
    # Arrange — INVARIANT
    # Act
    # Assert
    assert error_payload["exit_code"] == 1 and error_payload["errors"] == 1
