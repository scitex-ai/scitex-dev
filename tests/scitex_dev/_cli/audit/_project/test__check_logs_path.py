# -*- coding: utf-8 -*-
"""Tests for `_check_logs_path.py` (PS-223).

Convention (`_skills/general/02_package/15_cron-management.md`;
`jobs/_logsink.py`): a package's logs live under the gitignored
`~/.scitex/<pkg>/runtime/logs/` layer, never directly under
`~/.scitex/<pkg>/logs/`. PRs #367/#433 performed that migration; PS-223
mechanically prevents a regression back to the forbidden path.

Every fixture writes a REAL `.py` source file under `tmp_path/src/` at
RUNTIME — never a static repo file — so the self-audit
(`test_audit_all_clean`) never sees a forbidden path planted on disk.

`test_ps223_stays_silent_for_correct_runtime_logs_form` is the CONTROL ARM:
a mutation that makes the check flag every logs path must turn it red.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_logs_path import (
    check_ps223_logs_path,
)


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


class _StubConfig:
    """Minimal ProjectConfig stand-in exposing the exemption surface."""

    def __init__(self, accepted=(), errors=()):
        self._accepted = set(accepted)
        self.exemption_errors = tuple(errors)

    def exemption_for(self, rule: str, rel_path: str, line: int):
        return (rule, rel_path, line) in self._accepted or None


def _codes(out: list) -> list[str]:
    return [v.rule for v in out]


def _write_src(repo: Path, relpath: str, body: str) -> Path:
    """Write `body` to `repo/src/<relpath>` (parents created)."""
    target = repo / "src" / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _run(repo: Path, config=None) -> list:
    out: list = []
    check_ps223_logs_path(repo, _StubViolation, out, config=config)
    return out


# --- PS-223 fires: forbidden non-runtime logs path literal -------------------


def test_ps223_flags_forbidden_non_runtime_logs_path_literal(tmp_path: Path):
    # Arrange — an executed path literal at the forbidden location.
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        'LOG = "~/.scitex/dev/logs/cron-x.log"\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-223"]


def test_ps223_flags_home_env_prefixed_forbidden_path(tmp_path: Path):
    # Arrange — the `$HOME/...` prefix form is equally forbidden.
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        'p = "$HOME/.scitex/dev/logs/x.log"\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-223"]


def test_ps223_flags_fstring_literal_fragment(tmp_path: Path):
    # Arrange — an f-string's literal fragment is still a real path token.
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        'def f(name):\n    return f"~/.scitex/dev/logs/{name}.log"\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-223"]


def test_ps223_detail_names_the_offending_literal(tmp_path: Path):
    # Arrange
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        'LOG = "~/.scitex/dev/logs/cron-x.log"\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert — the remedy path is stated, not merely implied.
    assert "runtime/logs" in out[0].detail


# --- CONTROL ARM: the correct runtime/logs form stays clean ------------------


def test_ps223_stays_silent_for_correct_runtime_logs_form(tmp_path: Path):
    """CONTROL ARM — `runtime/logs/` is the convention, not a breach.

    A mutation that makes the check flag every logs path is caught HERE;
    every positive test above would still pass under such a mutation.
    """
    # Arrange
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        'LOG = "~/.scitex/dev/runtime/logs/cron-x.log"\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


# --- false-positive guards: prose is spared ----------------------------------


def test_ps223_does_not_fire_on_prose_docstring(tmp_path: Path):
    # Arrange — the forbidden path appears only in a module docstring.
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        '"""Historically logs lived at ~/.scitex/dev/logs/ before #367."""\n'
        "VALUE = 1\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


def test_ps223_does_not_fire_on_prose_comment(tmp_path: Path):
    # Arrange — the forbidden path appears only in a comment.
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        "# never ~/.scitex/dev/logs/ (the pre-#367 location)\n"
        "VALUE = 1\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


def test_ps223_does_not_fire_on_description_help_string_with_spaces(tmp_path: Path):
    # Arrange — a `description=` help string MENTIONS the path as prose
    # (full sentence, so it carries whitespace). This is the exact shape of
    # `status.py`'s help text and the ci-runner job descriptions.
    _write_src(
        tmp_path,
        "pkg/_status.py",
        "HELP = dict(\n"
        '    description="last-run mtime, falling back to the pre-cleanup '
        '~/.scitex/dev/logs/ path",\n'
        ")\n",
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


# --- one finding per offending literal ---------------------------------------


def test_ps223_emits_one_finding_per_offending_literal(tmp_path: Path):
    # Arrange
    _write_src(
        tmp_path,
        "pkg/_cron.py",
        'A = "~/.scitex/dev/logs/a.log"\nB = "~/.scitex/dev/logs/b.log"\n',
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-223", "PS-223"]


# --- exemptions --------------------------------------------------------------


def test_ps223_accepted_exemption_silences_the_named_site(tmp_path: Path):
    # Arrange — the literal is on line 1 of src/pkg/_legacy.py.
    _write_src(
        tmp_path,
        "pkg/_legacy.py",
        'LOG = "~/.scitex/dev/logs/legacy.log"\n',
    )
    cfg = _StubConfig(accepted={("PS-223", "src/pkg/_legacy.py", 1)})
    # Act
    out = _run(tmp_path, config=cfg)
    # Assert
    assert _codes(out) == []


def test_ps223_reports_rejected_exemption_entry_as_a_finding(tmp_path: Path):
    # Arrange — a clean tree, but a REJECTED exemption entry in the config.
    _write_src(tmp_path, "pkg/_ok.py", "VALUE = 1\n")
    cfg = _StubConfig(errors=("PS-223[0]: missing `reason`",))
    # Act
    out = _run(tmp_path, config=cfg)
    # Assert
    assert _codes(out) == ["PS-223"]


def test_ps223_rejected_exemption_for_another_rule_is_not_reported(tmp_path: Path):
    # Arrange — a rejection notice belonging to PS-220, not PS-223.
    _write_src(tmp_path, "pkg/_ok.py", "VALUE = 1\n")
    cfg = _StubConfig(errors=("PS-220[0]: missing `reason`",))
    # Act
    out = _run(tmp_path, config=cfg)
    # Assert
    assert _codes(out) == []


# --- registration ------------------------------------------------------------


def test_ps223_is_registered_at_severity_w():
    # Arrange
    from scitex_dev._cli.audit._project._registry import RULES

    # Act
    rule = RULES["PS-223"]
    # Assert — severity ships in the rule tuple (a co-located rule cannot be
    # reached by `_SEVERITY_OVERRIDES`; see `_registry.py` note by `_patch`).
    assert rule.severity == "W"


def test_ps223_is_registered_with_its_slug():
    # Arrange
    from scitex_dev._cli.audit._project._registry import RULES

    # Act
    rule = RULES["PS-223"]
    # Assert
    assert rule.slug == "non-runtime-logs-path"


# EOF
