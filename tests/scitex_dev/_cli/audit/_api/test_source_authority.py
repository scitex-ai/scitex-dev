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
    init = _repo(tmp_path, "src")
    result = _audit(tmp_path)
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["init"] == str(init)
    assert [v["rule"] for v in payload["violations"]] == ["PA-101"]
    assert payload["files_inspected"] >= 1


def test_requested_flat_checkout_is_audited(tmp_path):
    init = _repo(tmp_path, "")
    result = _audit(tmp_path)
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout)["init"] == str(init)


def test_missing_source_in_requested_checkout_is_not_clean_or_installed(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname="scitex-dev"\n')
    result = _audit(tmp_path)
    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert payload["init"] is None
    assert payload["status"] == "not-auditable"
    assert "installed fallback refused" in payload["detail"]


def test_source_without_violation_remains_auditable(tmp_path):
    init = _repo(tmp_path, "src")
    init.write_text("__all__ = []\n")
    result = _audit(tmp_path)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["init"] == str(init)
    assert payload["violations"] == []
    assert payload["files_inspected"] >= 1


def test_inspected_counter_excludes_ignored_build_and_venv_paths(tmp_path):
    init = _repo(tmp_path, "src")
    init.write_text("__all__ = []\n")
    for excluded in ("build", ".venv"):
        ignored = init.parent / excluded / "ignored.py"
        ignored.parent.mkdir()
        ignored.write_text("raise RuntimeError('ignored source must not execute')\n")
    result = _audit(tmp_path)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["files_inspected"] == 1
