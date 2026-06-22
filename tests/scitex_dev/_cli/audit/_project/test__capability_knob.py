"""Tests for the leaf-side package-type CAPABILITY knob.

A leaf declares ``audit.capabilities: [no-mcp, no-umbrella]`` in its
``.scitex/dev/config.yaml``; the auditor reads it and SKIPS the matching rule
with a VISIBLE "skipped (declared capability: X)" notice — not a silent pass
and not via the blanket ``audit.skip`` list. Each capability gates a FIXED set
of rule codes, so it can never silence an unrelated rule.

  no-mcp       -> skip the §6 MCP <-> Python-API parity check (alias pkgs).
  no-umbrella  -> skip PS-501 / PS-503 (examples must use @stx.session).

Operator directive 2026-06-22.
"""

from __future__ import annotations

import contextlib
import io
import json as _json
from pathlib import Path

import pytest

from scitex_dev._cli.audit._config import (
    CAPABILITY_RULES,
    KNOWN_CAPABILITIES,
    capability_for_rule,
    load_config,
)
from scitex_dev._cli.audit._project import audit_project
from scitex_dev._cli.audit._summary._mcp_parity import (
    _check_api_parity,
    declares_no_mcp,
)


# ---------------------------------------------------------------------------
# helpers + fixtures
# ---------------------------------------------------------------------------


def _write_config(repo: Path, capabilities: list[str] | None) -> None:
    """Write a `.scitex/dev/config.yaml` for `repo`, optionally with caps."""
    cfg_dir = repo / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    body = "project-type:\n  - pip\n"
    if capabilities is not None:
        body += "audit:\n  capabilities:\n"
        for cap in capabilities:
            body += f"    - {cap}\n"
    (cfg_dir / "config.yaml").write_text(body, encoding="utf-8")


def _make_ps501_repo(tmp_path: Path, capabilities: list[str] | None) -> Path:
    """A package whose examples/01_*.py has main() but no @stx.session (PS-501)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    examples = tmp_path / "examples"
    examples.mkdir()
    (examples / "01_demo.py").write_text(
        'def main():\n    print("hi")\n\n\nif __name__ == "__main__":\n    main()\n',
        encoding="utf-8",
    )
    _write_config(tmp_path, capabilities)
    return tmp_path


def _make_alias_repo(tmp_path: Path, capabilities: list[str] | None) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-plt"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    _write_config(tmp_path, capabilities)
    return tmp_path


def _audit_json(repo: Path, rules: set[str]) -> dict:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        audit_project(
            "demo-pkg", repo=repo, json_out=True, rules=rules, severity="info"
        )
    return _json.loads(buf.getvalue())


# ---------------------------------------------------------------------------
# loader — the knob's fixed contract
# ---------------------------------------------------------------------------


def test_known_capabilities_are_no_mcp_and_no_umbrella():
    # Arrange
    expected = frozenset({"no-mcp", "no-umbrella"})
    # Act
    actual = KNOWN_CAPABILITIES
    # Assert
    assert actual == expected


def test_no_mcp_gates_section6_rule():
    # Arrange
    # Act
    gated = CAPABILITY_RULES["no-mcp"]
    # Assert
    assert gated == frozenset({"§6"})


def test_no_umbrella_gates_ps501_and_ps503():
    # Arrange
    # Act
    gated = CAPABILITY_RULES["no-umbrella"]
    # Assert
    assert gated == frozenset({"PS-501", "PS-503"})


def test_capability_for_section6_is_no_mcp():
    # Arrange
    # Act
    cap = capability_for_rule("§6")
    # Assert
    assert cap == "no-mcp"


def test_capability_for_ps501_is_no_umbrella():
    # Arrange
    # Act
    cap = capability_for_rule("PS-501")
    # Assert
    assert cap == "no-umbrella"


def test_capability_for_ungated_rule_is_none():
    # Arrange
    # Act
    cap = capability_for_rule("PS-101")
    # Assert
    assert cap is None


def test_load_config_keeps_known_capabilities(tmp_path):
    # Arrange
    _write_config(tmp_path, ["no-mcp", "no-umbrella", "totally-bogus"])
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.capabilities == frozenset({"no-mcp", "no-umbrella"})


def test_load_config_drops_unknown_capability(tmp_path):
    # Arrange
    _write_config(tmp_path, ["no-mcp", "totally-bogus"])
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.has_capability("totally-bogus") is False


def test_load_config_has_no_capabilities_when_absent(tmp_path):
    # Arrange
    _write_config(tmp_path, capabilities=None)
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.capabilities == frozenset()


def test_load_config_honours_audit_block_without_project_type(tmp_path):
    # Arrange — a config that declares ONLY an audit block (no project-type),
    # like an alias package's capability knob. The audit block must still
    # apply (types fall back to heuristic detection).
    cfg_dir = tmp_path / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.yaml").write_text(
        "audit:\n  capabilities:\n    - no-mcp\n", encoding="utf-8"
    )
    # Act
    cfg = load_config(tmp_path)
    # Assert
    assert cfg.has_capability("no-mcp") is True


# ---------------------------------------------------------------------------
# no-umbrella -> PS-501 / PS-503
# ---------------------------------------------------------------------------


def test_ps501_fires_without_capability(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=None)
    # Act
    payload = _audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert {v["rule"] for v in payload["violations"]} == {"PS-501"}


def test_ps501_not_skipped_without_capability(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=None)
    # Act
    payload = _audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert payload["capability_skips"] == []


def test_ps501_dropped_with_no_umbrella(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    payload = _audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert payload["violations"] == []


def test_ps501_skip_is_clean_exit_with_no_umbrella(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    payload = _audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert payload["exit_code"] == 0


def test_ps501_skip_is_recorded_visibly_in_json(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    payload = _audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert {"rule": "PS-501", "capability": "no-umbrella"} in payload[
        "capability_skips"
    ]


def test_ps501_skip_emits_human_notice(tmp_path, capsys):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-umbrella"])
    # Act
    audit_project("demo-pkg", repo=repo, rules={"PS-501"}, severity="info")
    # Assert
    assert "skipped (declared capability: no-umbrella)" in capsys.readouterr().err


def test_no_mcp_does_not_skip_ps501(tmp_path):
    # Arrange
    repo = _make_ps501_repo(tmp_path, capabilities=["no-mcp"])
    # Act
    payload = _audit_json(repo, rules={"PS-501", "PS-503"})
    # Assert
    assert {v["rule"] for v in payload["violations"]} == {"PS-501"}


# ---------------------------------------------------------------------------
# no-mcp -> §6 MCP <-> Python-API parity
# ---------------------------------------------------------------------------


def test_declares_no_mcp_true_with_capability(tmp_path):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=["no-mcp"])
    # Act
    result = declares_no_mcp("scitex-plt", repo=repo)
    # Assert
    assert result is True


def test_declares_no_mcp_false_without_capability(tmp_path):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=None)
    # Act
    result = declares_no_mcp("scitex-plt", repo=repo)
    # Assert
    assert result is False


def test_parity_check_emits_no_violations_with_no_mcp(tmp_path):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=["no-mcp"])
    out: list = []
    # Act
    _check_api_parity("scitex-plt", {"plt_orphan_tool"}, out, repo=repo)
    # Assert
    assert out == []


def test_parity_check_emits_capability_notice_with_no_mcp(tmp_path, capsys):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=["no-mcp"])
    out: list = []
    # Act
    _check_api_parity("scitex-plt", {"plt_orphan_tool"}, out, repo=repo)
    # Assert
    assert "skipped (declared capability: no-mcp)" in capsys.readouterr().err


if __name__ == "__main__":
    pytest.main([__file__, "-x", "-q"])
