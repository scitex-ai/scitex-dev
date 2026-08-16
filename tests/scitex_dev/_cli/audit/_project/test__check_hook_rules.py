#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: tests/scitex_dev/_cli/audit/_project/test__check_hook_rules.py
"""PS-HOOK-010/011/012 — declared-guardrail audit rules.

Each rule has at least one test that DRIVES A VIOLATING CASE (proving the gate
can go red) and an explicit CONTROL ARM (proving it can stay green). A gate
that cannot fail is not a gate; a gate that always fires is not one either.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_hook_rules import check_hook_rules


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


class _StubConfig:
    """Minimal ProjectConfig stand-in exposing the exemption surface."""

    def __init__(self, accepted=()):
        self._accepted = set(accepted)
        self.exemption_errors = ()

    def exemption_for(self, rule: str, rel_path: str, line: int):
        return (rule, rel_path, line) in self._accepted or None


def _codes(out: list) -> list[str]:
    return [v.rule for v in out]


def _write_src(repo: Path, relpath: str, body: str) -> Path:
    target = repo / "src" / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def _run(repo: Path, config=None) -> list:
    out: list = []
    check_hook_rules(repo, _StubViolation, out, config=config)
    return out


_GOOD_REASON = "Because the thing broke production on 2026-08-12, measured."


def _decl(**over) -> str:
    fields = dict(
        id='"pkg.some-rule"',
        rule='"Refuse the thing."',
        reason=f'"{_GOOD_REASON}"',
        event='"pre-tool-use"',
        severity='"deny"',
        matches='("Bash",)',
        provider='"pkg"',
    )
    fields.update(over)
    body = ",\n        ".join(f"{k}={v}" for k, v in fields.items())
    return (
        "from scitex_dev.hooks import HookRule\n\n"
        "def provide():\n"
        "    return [\n"
        f"        HookRule(\n        {body},\n        ),\n"
        "    ]\n"
    )


# --- PS-HOOK-011 fires: a binding that resolves nowhere ----------------------


def test_ps_hook_011_flags_a_script_that_does_not_exist(tmp_path: Path):
    # Arrange
    _write_src(tmp_path, "pkg/_hook_rules.py", _decl(script='"hooks/ghost.sh"'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-HOOK-011"]


def test_ps_hook_011_flags_a_predicate_that_does_not_exist(tmp_path: Path):
    # Arrange
    _write_src(tmp_path, "pkg/hooks/real.sh", "#!/bin/sh\n")
    _write_src(
        tmp_path,
        "pkg/_hook_rules.py",
        _decl(script='"hooks/real.sh"', predicate='"hooks/ghost.py"'),
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-HOOK-011"]


def test_ps_hook_011_is_silenced_by_a_declared_exemption(tmp_path: Path):
    # Arrange
    _write_src(tmp_path, "pkg/_hook_rules.py", _decl(script='"hooks/ghost.sh"'))
    config = _StubConfig(accepted=[("PS-HOOK-011", "src/pkg/_hook_rules.py", 5)])
    # Act
    out = _run(tmp_path, config=config)
    # Assert
    assert _codes(out) == []


# --- PS-HOOK-011 CONTROL ARM -------------------------------------------------


def test_ps_hook_011_stays_silent_when_the_script_ships(tmp_path: Path):
    """CONTROL ARM — a binding that RESOLVES is the convention, not a breach.

    A mutation that flagged every declared script would be caught HERE; the
    positive tests above would still pass under it.
    """
    # Arrange
    _write_src(tmp_path, "pkg/hooks/real.sh", "#!/bin/sh\n")
    _write_src(tmp_path, "pkg/_hook_rules.py", _decl(script='"hooks/real.sh"'))
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


def test_ps_hook_011_skips_a_non_literal_binding(tmp_path: Path):
    """A path built at runtime is not statically resolvable, so do not guess."""
    # Arrange
    _write_src(tmp_path, "pkg/_hook_rules.py", _decl(script="_PATH"))
    # Act
    out = _run(tmp_path)
    # Assert
    assert "PS-HOOK-011" not in _codes(out)


# --- PS-HOOK-012 fires: a reason with no substance ---------------------------


def test_ps_hook_012_flags_a_placeholder_reason(tmp_path: Path):
    # Arrange
    _write_src(
        tmp_path,
        "pkg/_hook_rules.py",
        _decl(reason='"TODO"', implemented_in='"dotfiles:x.sh"', script="None"),
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-HOOK-012"]


def test_ps_hook_012_flags_a_reason_too_short_to_say_anything(tmp_path: Path):
    # Arrange
    _write_src(
        tmp_path,
        "pkg/_hook_rules.py",
        _decl(reason='"it is bad"', implemented_in='"dotfiles:x.sh"', script="None"),
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-HOOK-012"]


# --- PS-HOOK-012 CONTROL ARM -------------------------------------------------


def test_ps_hook_012_stays_silent_for_a_substantive_reason(tmp_path: Path):
    """CONTROL ARM — a real reason must not be flagged."""
    # Arrange
    _write_src(
        tmp_path,
        "pkg/_hook_rules.py",
        _decl(implemented_in='"dotfiles:x.sh"', script="None"),
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


# --- PS-HOOK-010 fires: scripts enforce, nothing declares them ---------------


def test_ps_hook_010_flags_undeclared_agent_hook_scripts(tmp_path: Path):
    # Arrange
    hooks = tmp_path / "src" / "pkg" / "agent_hooks"
    hooks.mkdir(parents=True)
    (hooks / "deny_thing.sh").write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\n', "utf-8")
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == ["PS-HOOK-010"]


# --- PS-HOOK-010 CONTROL ARMS ------------------------------------------------


def test_ps_hook_010_stays_silent_once_a_rule_declares_them(tmp_path: Path):
    """CONTROL ARM — declaring the guardrail is exactly the fix."""
    # Arrange
    hooks = tmp_path / "src" / "pkg" / "agent_hooks"
    hooks.mkdir(parents=True)
    (hooks / "deny_thing.sh").write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    _write_src(
        tmp_path, "pkg/_hook_rules.py", _decl(script='"agent_hooks/deny_thing.sh"')
    )
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


def test_ps_hook_010_spares_git_hook_trees(tmp_path: Path):
    """CONTROL ARM — `_hooks/` is git plumbing, governed by PS-HOOK-001."""
    # Arrange
    hooks = tmp_path / "src" / "pkg" / "_hooks"
    hooks.mkdir(parents=True)
    (hooks / "run_lint.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\n', "utf-8")
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []


def test_ps_hook_010_stays_silent_for_a_repo_with_no_agent_hooks(tmp_path: Path):
    """CONTROL ARM — the overwhelming majority of repos must see nothing."""
    # Arrange
    _write_src(tmp_path, "pkg/__init__.py", "\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "pkg"\n', "utf-8")
    # Act
    out = _run(tmp_path)
    # Assert
    assert _codes(out) == []
