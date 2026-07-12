"""Tests for ``scitex-dev host`` — the CLI surface (click wiring).

Drives `host list` / `host show` / `host resolve` through `CliRunner`
against a real temp `hosts.yaml` (`--hosts-file`, never the real
`~/.scitex/dev/hosts.yaml`). Engine-level coverage (resolve()/
list_hosts() semantics, error shapes) lives in
`tests/scitex_dev/hosts/test__registry.py`.

No mocks (NM001-003) — real temp files. One assert per test
(02_package/13_test-quality.md).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli._root import main

_TWO_HOST_YAML = """\
hosts:
  mba:
    kind: workstation
    ssh_alias: mba
    scitex_root: "~/.scitex"
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
"""


def _write_hosts_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "hosts.yaml"
    p.write_text(_TWO_HOST_YAML)
    return p


def _run(args: list[str]):
    runner = CliRunner()
    return runner.invoke(main, args)


# -------- host list ---------------------------------------------------------


def test_list_exit_code_zero(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "list", "--hosts-file", str(p)])
    # Assert
    assert result.exit_code == 0


def test_list_human_output_contains_mba(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "list", "--hosts-file", str(p)])
    # Assert
    assert "mba" in result.output


def test_list_human_output_contains_spartan(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "list", "--hosts-file", str(p)])
    # Assert
    assert "spartan" in result.output


def test_list_json_output_is_valid_json(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "list", "--hosts-file", str(p), "--json"])
    # Assert
    payload = json.loads(result.output)
    assert "hosts" in payload


def test_list_json_output_has_two_entries(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "list", "--hosts-file", str(p), "--json"])
    # Assert
    payload = json.loads(result.output)
    assert len(payload["hosts"]) == 2


def test_list_empty_registry_reports_none_registered(tmp_path):
    # Arrange
    p = tmp_path / "hosts.yaml"
    p.write_text("hosts: {}\n")
    # Act
    result = _run(["host", "list", "--hosts-file", str(p)])
    # Assert
    assert "no hosts registered" in result.output


# -------- host show ----------------------------------------------------------


def test_show_exit_code_zero(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "show", "spartan", "--hosts-file", str(p)])
    # Assert
    assert result.exit_code == 0


def test_show_human_output_contains_kind(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "show", "spartan", "--hosts-file", str(p)])
    # Assert
    assert "hpc-login" in result.output


def test_show_json_output_matches_record(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "show", "spartan", "--hosts-file", str(p), "--json"])
    # Assert
    payload = json.loads(result.output)
    assert payload["name"] == "spartan"


def test_show_unknown_host_exits_nonzero(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "show", "nonexistent", "--hosts-file", str(p)])
    # Assert
    assert result.exit_code != 0


def test_show_unknown_host_error_message_is_actionable(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "show", "nonexistent", "--hosts-file", str(p)])
    # Assert
    assert "Registered hosts" in result.output


# -------- host resolve --------------------------------------------------------


def test_resolve_field_scitex_root_prints_value(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(
        ["host", "resolve", "spartan", "--field", "scitex_root", "--hosts-file", str(p)]
    )
    # Assert
    assert result.output.strip() == "/data/gpfs/projects/punim0264/ywatanabe/.scitex"


def test_resolve_field_kind_prints_value(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(
        ["host", "resolve", "spartan", "--field", "kind", "--hosts-file", str(p)]
    )
    # Assert
    assert result.output.strip() == "hpc-login"


def test_resolve_field_ssh_alias_local_host_prints_empty(tmp_path):
    # Arrange
    yaml_text = (
        "hosts:\n"
        "  ywata-note-win:\n"
        "    kind: workstation\n"
        "    ssh_alias: null\n"
        '    scitex_root: "~/.scitex"\n'
    )
    p = tmp_path / "hosts.yaml"
    p.write_text(yaml_text)
    # Act
    result = _run(
        [
            "host",
            "resolve",
            "ywata-note-win",
            "--field",
            "ssh_alias",
            "--hosts-file",
            str(p),
        ]
    )
    # Assert
    assert result.output.strip() == ""


def test_resolve_exit_code_zero_on_known_host(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(
        ["host", "resolve", "spartan", "--field", "scitex_root", "--hosts-file", str(p)]
    )
    # Assert
    assert result.exit_code == 0


def test_resolve_unknown_host_exits_nonzero(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(
        [
            "host",
            "resolve",
            "nonexistent",
            "--field",
            "scitex_root",
            "--hosts-file",
            str(p),
        ]
    )
    # Assert
    assert result.exit_code != 0


def test_resolve_missing_field_option_exits_nonzero(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(["host", "resolve", "spartan", "--hosts-file", str(p)])
    # Assert
    assert result.exit_code != 0


def test_resolve_invalid_field_choice_exits_nonzero(tmp_path):
    # Arrange
    p = _write_hosts_yaml(tmp_path)
    # Act
    result = _run(
        ["host", "resolve", "spartan", "--field", "not-a-field", "--hosts-file", str(p)]
    )
    # Assert
    assert result.exit_code != 0


# -------- bare `host` group -------------------------------------------------


def test_bare_host_shows_help():
    # Arrange
    # Act
    result = _run(["host"])
    # Assert
    assert "host registry" in result.output.lower()


# EOF
