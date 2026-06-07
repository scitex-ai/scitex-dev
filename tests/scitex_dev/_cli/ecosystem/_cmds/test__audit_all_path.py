"""Tests for `scitex-dev ecosystem audit-all --path PATH`.

Lead task #40 part (a): worktree-based agents must be able to point
``audit-all`` at an explicit checkout (the worktree they're editing in)
instead of resolving the package NAME to the registry's local_path /
the editable install location.

The three sub-auditors that already understand a repo path
(``audit-project`` / ``audit-django`` / ``audit-python-apis``) gain
``--path`` as an alias for the existing ``--repo``; the three that
don't (``audit-cli`` / ``audit-mcp-tools`` / ``audit-skills``) are
intentionally NOT extended in this PR — they audit the registry-
resolved location and a follow-up will surface a path-aware variant.

PA-306 no-mocks: we exercise the real Click command + a real PATH-
shimmed `scitex-dev` binary that records its argv to a tmpfile.
Click's CliRunner accepts an ``env=`` kwarg, so no ``monkeypatch`` is
needed (the existing test_audit_all.py uses the same pattern).

PA-307 test-quality: every test has the canonical
``# Arrange`` / ``# Act`` / ``# Assert`` markers and a single
assertion (rule splits the multi-assert tests below).
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

pytest.importorskip("click")


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# audit-project / audit-django / audit-python-apis: --path alias of --repo.
# One assertion per test (split so each `assert "--path" in ...` /
# `assert "--repo" in ...` is its own function).
# ---------------------------------------------------------------------------


def test_audit_project_help_advertises_path_flag(runner):
    """--path appears in audit-project --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-project", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_project_help_retains_repo_alias(runner):
    """--repo still appears in audit-project --help (back-compat alias)."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-project", "--help"])
    # Assert
    assert "--repo" in result.output


def test_audit_django_help_advertises_path_flag(runner):
    """--path appears in audit-django --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-django", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_django_help_retains_repo_alias(runner):
    """--repo still appears in audit-django --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-django", "--help"])
    # Assert
    assert "--repo" in result.output


def test_audit_python_apis_help_advertises_path_flag(runner):
    """--path appears in audit-python-apis --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-python-apis", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_python_apis_help_retains_repo_alias(runner):
    """--repo still appears in audit-python-apis --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-python-apis", "--help"])
    # Assert
    assert "--repo" in result.output


# ---------------------------------------------------------------------------
# audit-all help mentions --path and worktree context.
# ---------------------------------------------------------------------------


def test_audit_all_help_advertises_path_flag(runner):
    """--path appears in audit-all --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-all", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_all_help_mentions_worktree_use_case(runner):
    """The --path help blurb references the worktree pain point."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-all", "--help"])
    # Assert
    assert "worktree" in result.output


def test_audit_all_path_with_multiple_distributions_errors(runner, tmp_path):
    """audit-all --path /some/path scitex-io scitex-stats → exit 2."""
    # Arrange
    from scitex_dev._cli._root import main

    repo = tmp_path / "fake-checkout"
    repo.mkdir()
    # Act
    result = runner.invoke(
        main,
        [
            "ecosystem",
            "audit-all",
            "--path",
            str(repo),
            "scitex-io",
            "scitex-stats",
        ],
    )
    # Assert
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# audit-all --path: thread-through fan-out. PATH-shim a fake `scitex-dev`
# that records every argv it sees; assert per-auditor expectations one
# at a time. One assertion per test, AAA markers throughout.
# ---------------------------------------------------------------------------


def _install_shim(shim_dir: Path, log: Path) -> Path:
    """Drop a real `scitex-dev` script that records its argv to ``log``.

    The shim is a posix shell script that writes one argv per line so
    the tests can introspect what flags actually got passed.
    """
    script = shim_dir / "scitex-dev"
    script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\nexit 0\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def _shim_env(shim_dir: Path) -> dict[str, str]:
    """Build an env-dict that puts the shim's PATH first."""
    return {
        **os.environ,
        "PATH": f"{shim_dir}{os.pathsep}{os.environ['PATH']}",
    }


def _run_with_path(runner, tmp_path: Path, *cli_args):
    """Invoke audit-all with a shim on PATH; return (log, result)."""
    from scitex_dev._cli._root import main

    log = tmp_path / "argv.log"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    _install_shim(shim_dir, log)
    result = runner.invoke(
        main,
        ["ecosystem", "audit-all", "--no-version-check", *cli_args],
        env=_shim_env(shim_dir),
        catch_exceptions=False,
    )
    return log, result


def _argvs_by_auditor(log: Path) -> dict[str, list[str]]:
    """Parse the shim's log into ``{auditor_name: argv_list}``."""
    out: dict[str, list[str]] = {}
    for ln in log.read_text().splitlines():
        argv = ln.split()
        if len(argv) >= 2 and argv[0] == "ecosystem":
            out[argv[1]] = argv
    return out


def test_audit_all_with_path_exits_zero(runner, tmp_path):
    """The shim returns 0 for every audit; the dispatcher must exit 0."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    _, result = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert result.exit_code == 0


def test_audit_all_with_path_threads_to_audit_project(runner, tmp_path):
    """audit-project must receive --path REPO."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" in _argvs_by_auditor(log).get("audit-project", [])


def test_audit_all_with_path_threads_to_audit_django(runner, tmp_path):
    """audit-django must receive --path REPO."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" in _argvs_by_auditor(log).get("audit-django", [])


def test_audit_all_with_path_threads_to_audit_python_apis(runner, tmp_path):
    """audit-python-apis must receive --path REPO."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" in _argvs_by_auditor(log).get("audit-python-apis", [])


def test_audit_all_with_path_skips_audit_cli(runner, tmp_path):
    """audit-cli must NOT receive --path (not yet path-aware)."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" not in _argvs_by_auditor(log).get("audit-cli", [])


def test_audit_all_with_path_skips_audit_mcp_tools(runner, tmp_path):
    """audit-mcp-tools must NOT receive --path (not yet path-aware)."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" not in _argvs_by_auditor(log).get("audit-mcp-tools", [])


def test_audit_all_with_path_skips_audit_skills(runner, tmp_path):
    """audit-skills must NOT receive --path (not yet path-aware)."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" not in _argvs_by_auditor(log).get("audit-skills", [])


def test_audit_all_without_path_does_not_pass_path_arg(runner, tmp_path):
    """When --path is omitted, no sub-auditor argv contains --path."""
    # Arrange — only `scitex-io` is passed; no --path
    # Act
    log, _ = _run_with_path(runner, tmp_path, "scitex-io")
    # Assert
    assert not any("--path" in argv for argv in _argvs_by_auditor(log).values())
