"""A requested checkout must beat the auditor's real installed package."""

from __future__ import annotations

import json

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem import register_ecosystem_commands


def _audit(root):
    @click.group()
    def command():
        pass

    register_ecosystem_commands(command)
    return CliRunner().invoke(
        command,
        [
            "ecosystem", "audit-python-apis", "scitex-dev", "--path", str(root),
            "--rule", "PA-101", "--json",
        ],
    )


def _repo(tmp_path, layout):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="scitex-dev"\n')
    package = tmp_path / layout / "scitex_dev" if layout else tmp_path / "scitex_dev"
    package.mkdir(parents=True)
    init = package / "__init__.py"
    # Static audit must observe the missing __all__, without executing this.
    init.write_text("raise RuntimeError('consumer source must never execute')\n")
    return init


def test_requested_src_checkout_is_audited_not_real_installed_dev(tmp_path):
    # Arrange
    init = _repo(tmp_path, "src")
    # Act
    result = _audit(tmp_path)
    payload = json.loads(result.stdout)
    observed = (result.exit_code, payload["init"],
                [v["rule"] for v in payload["violations"]],
                payload["files_inspected"] >= 1)
    # Assert
    assert observed == (1, str(init), ["PA-101"], True), result.output


def test_requested_flat_checkout_is_audited(tmp_path):
    # Arrange
    init = _repo(tmp_path, "")
    # Act
    result = _audit(tmp_path)
    observed = (result.exit_code, json.loads(result.stdout)["init"])
    # Assert
    assert observed == (1, str(init)), result.output


def test_missing_source_in_requested_checkout_is_not_clean_or_installed(tmp_path):
    # Arrange
    (tmp_path / "pyproject.toml").write_text('[project]\nname="scitex-dev"\n')
    # Act
    result = _audit(tmp_path)
    payload = json.loads(result.stdout)
    observed = (result.exit_code, payload["init"], payload["status"],
                "installed fallback refused" in payload["detail"])
    # Assert
    assert observed == (2, None, "not-auditable", True), result.output


def test_source_without_violation_remains_auditable(tmp_path):
    # Arrange
    init = _repo(tmp_path, "src")
    init.write_text("__all__ = []\n")
    # Act
    result = _audit(tmp_path)
    payload = json.loads(result.stdout)
    observed = (result.exit_code, payload["init"], payload["violations"],
                payload["files_inspected"] >= 1)
    # Assert
    assert observed == (0, str(init), [], True), result.output


def test_inspected_counter_excludes_ignored_build_and_venv_paths(tmp_path):
    # Arrange
    init = _repo(tmp_path, "src")
    init.write_text("__all__ = []\n")
    for excluded in ("build", ".venv"):
        ignored = init.parent / excluded / "ignored.py"
        ignored.parent.mkdir()
        ignored.write_text("raise RuntimeError('ignored source must not execute')\n")
    # Act
    result = _audit(tmp_path)
    observed = (result.exit_code, json.loads(result.stdout)["files_inspected"])
    # Assert
    assert observed == (0, 1), result.output
