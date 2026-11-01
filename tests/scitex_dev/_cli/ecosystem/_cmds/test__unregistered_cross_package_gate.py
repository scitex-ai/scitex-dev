"""Exercise the real generator against an unregistered package checkout."""

import subprocess

import click
from click.testing import CliRunner

from scitex_dev._cli.ecosystem._cmds._install_cross_package_gate import register


def _package(tmp_path):
    repo = tmp_path / "unregistered-leaf"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-unregistered-demo"\n'
    )
    src = repo / "src" / "scitex_unregistered_demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("import scitex_sdk.app\n")
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    return repo


def _cli():
    group = click.Group()
    register(group)
    return group


def test_unregistered_checkout_generates_real_collected_imports(tmp_path, monkeypatch):
    repo = _package(tmp_path)
    monkeypatch.chdir(repo / "src")
    result = CliRunner().invoke(
        _cli(), ["install-cross-package-gate", "scitex-unregistered-demo"]
    )
    gate = repo / "tests/integration/test_cross_package_imports.py"
    assert result.exit_code == 0, result.output
    assert "'scitex_sdk.app'" in gate.read_text()
    assert "cwd repository" in result.output


def test_explicit_unregistered_target_still_refuses_identity_mismatch(tmp_path):
    repo = _package(tmp_path)
    result = CliRunner().invoke(
        _cli(), ["install-cross-package-gate", "scitex-wrong-demo", "--path", str(repo)]
    )
    assert result.exit_code == 2
    assert "target tree is NOT" in result.output
    assert not (repo / "tests").exists()


def test_explicit_unregistered_target_dry_run_does_not_write(tmp_path):
    repo = _package(tmp_path)
    result = CliRunner().invoke(
        _cli(),
        [
            "install-cross-package-gate",
            "scitex-unregistered-demo",
            "--path",
            str(repo),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "'scitex_sdk.app'" in result.output
    assert not (repo / "tests").exists()
