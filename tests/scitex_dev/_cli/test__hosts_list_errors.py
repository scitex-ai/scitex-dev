"""Host list uses the established registry-error boundary and keeps valid output."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from scitex_dev._cli._root import main

_BAD = ['[]\n', 'hosts: []\n', 'hosts: [unterminated\n', 'hosts:\n  broken: []\n']


@pytest.mark.parametrize("document", _BAD)
@pytest.mark.parametrize("as_json", [False, True])
def test_list_registry_error_has_declared_code_and_stderr(
    tmp_path: Path, document: str, as_json: bool
) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text(document, encoding="utf-8")
    args = ["host", "list", "--hosts-file", str(path)] + (["--json"] if as_json else [])
    # Act
    result = CliRunner().invoke(main, args)
    # Assert
    assert (result.exit_code, result.stdout, str(path) in result.stderr) == (2, "", True)


@pytest.mark.parametrize("as_json", [False, True])
def test_list_empty_registry_keeps_success_output(tmp_path: Path, as_json: bool) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text("hosts: {}\n", encoding="utf-8")
    args = ["host", "list", "--hosts-file", str(path)] + (["--json"] if as_json else [])
    # Act
    result = CliRunner().invoke(main, args)
    value = json.loads(result.stdout) if as_json else result.stdout.strip()
    # Assert
    assert (result.exit_code, result.stderr, value) == (
        0, "", {"hosts": []} if as_json else "(no hosts registered)"
    )


@pytest.mark.parametrize("as_json", [False, True])
def test_list_valid_record_keeps_success_output(tmp_path: Path, as_json: bool) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_text('hosts:\n  owned-host:\n    kind: storage\n    scitex_root: "/owned/state"\n')
    args = ["host", "list", "--hosts-file", str(path)] + (["--json"] if as_json else [])
    # Act
    result = CliRunner().invoke(main, args)
    contains_record = (
        json.loads(result.stdout)["hosts"][0]["name"] == "owned-host"
        if as_json else "owned-host" in result.stdout and "/owned/state" in result.stdout
    )
    # Assert
    assert (result.exit_code, result.stderr, contains_record) == (0, "", True)


def test_list_does_not_mask_unexpected_decode_error(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "hosts.yaml"
    path.write_bytes(b"\xff")
    # Act
    result = CliRunner().invoke(main, ["host", "list", "--hosts-file", str(path)])
    # Assert
    assert isinstance(result.exception, UnicodeDecodeError)
