"""Direct file-gate calls obey the existing new-only refusal."""

import importlib
import subprocess

import click
import pytest

from scitex_dev.linter._forbid_new_only import FORBIDDEN_NEW_ONLY


@pytest.fixture(params=[(module, state) for module in ["_cmd_check", "cli"] for state in ["clean", "preexisting", "missing"]])
def direct_gate_case(request, tmp_path):
    module, state = request.param
    handler = importlib.import_module("scitex_dev.linter." + module)._do_check
    (tmp_path / "pyproject.toml").write_text('[tool.scitex-dev.linter]\nlibrary_dirs = ["."]\nper-rule-severity = { "STX-NL001" = "error" }\n')
    file = tmp_path / "owned.py"
    file.write_text("x = 1234\n" if state == "preexisting" else "VALUE = 1\n")
    for args in [("init",), ("config", "user.email", "owned@example.invalid"), ("config", "user.name", "Owned test"), ("add", "."), ("commit", "-m", "baseline")]:
        subprocess.run(["git", "-C", str(tmp_path), *args], capture_output=True, check=True)
    if state == "missing":
        file.unlink()
    return handler, str(file), 0 if state == "clean" else 2


def test_direct_gate_refuses_new_only(direct_gate_case):
    # Arrange
    handler, path, _ = direct_gate_case
    # Act
    # Assert
    with pytest.raises(click.UsageError, match="禁止"):
        handler(path, as_json=False, no_color=True, severity="error", category=None, new_only=True)


@pytest.fixture
def direct_gate_error(direct_gate_case):
    handler, path, _ = direct_gate_case
    with pytest.raises(click.UsageError) as error:
        handler(path, as_json=True, no_color=True, severity="error", category=None, new_only=True)
    return error.value


def test_direct_gate_uses_the_existing_full_refusal_message(direct_gate_error):
    # Arrange
    # Act
    message = direct_gate_error.message
    # Assert
    assert message == FORBIDDEN_NEW_ONLY


def test_direct_gate_normal_mode_keeps_full_severity_and_exit(direct_gate_case):
    # Arrange
    handler, path, expected_exit = direct_gate_case
    # Act
    result = handler(path, as_json=False, no_color=True, severity="error", category=None, new_only=False)
    # Assert
    assert result == expected_exit
