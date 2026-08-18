"""Tests for `scitex-dev ecosystem audit-all --path PATH`.

Lead task #40 part (a): worktree-based agents must be able to point
``audit-all`` at an explicit checkout (the worktree they're editing in)
instead of resolving the package NAME to the registry's local_path /
the editable install location.

ALL SIX sub-auditors now honour ``--path`` (alias ``--repo``) and
resolve their target tree through the SAME shared ``resolve_target_tree``:
``audit-project`` / ``audit-django`` / ``audit-python-apis`` (the
original three) plus ``audit-cli`` / ``audit-mcp-tools`` /
``audit-skills`` (the follow-up this file's ``…threads_to_audit_cli`` /
``…mcp_tools`` / ``…skills`` cases now assert). ``audit-all`` therefore
threads ``--path`` to every sub-auditor uniformly instead of silently
letting three grade the registry/import-location tree.

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
# audit-cli / audit-mcp-tools / audit-skills: newly gained --path (+ --repo).
# One assertion per test.
# ---------------------------------------------------------------------------


def test_audit_cli_help_advertises_path_flag(runner):
    """--path appears in audit-cli --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-cli", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_cli_help_retains_repo_alias(runner):
    """--repo appears in audit-cli --help (back-compat alias)."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-cli", "--help"])
    # Assert
    assert "--repo" in result.output


def test_audit_mcp_tools_help_advertises_path_flag(runner):
    """--path appears in audit-mcp-tools --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-mcp-tools", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_mcp_tools_help_retains_repo_alias(runner):
    """--repo appears in audit-mcp-tools --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-mcp-tools", "--help"])
    # Assert
    assert "--repo" in result.output


def test_audit_skills_help_advertises_path_flag(runner):
    """--path appears in audit-skills --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-skills", "--help"])
    # Assert
    assert "--path" in result.output


def test_audit_skills_help_retains_repo_alias(runner):
    """--repo appears in audit-skills --help."""
    # Arrange
    from scitex_dev._cli._root import main

    # Act
    result = runner.invoke(main, ["ecosystem", "audit-skills", "--help"])
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

    It ALSO echoes one framing line to stdout, because every real auditor
    does (`INFO: <pkg>: auditing <path>`) and the dispatcher now refuses to
    issue a verdict over zero inspected lines. A shim that printed nothing
    made these tests assert that SILENCE MEANS PASS — the exact behaviour
    measured on the CI SIF's baked 0.42.0, which returned a verdict having
    read nothing. The argv log is unaffected; it was never stdout.
    """
    script = shim_dir / "scitex-dev"
    script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\n"
        "echo 'INFO: shim: auditing (no findings)'\nexit 0\n",
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
    # The auditor is selected by pointing the INTERPRETER at the shim: the
    # launcher is `sys.executable -m scitex_dev`, not a PATH lookup (sac's
    # P1). `_audit_all` imports sys inside the command function, so there is
    # no module attribute to patch — the local import binds the real module,
    # and patching `sys.executable` reaches it.
    #
    # `_shim_env` still puts the shim on PATH deliberately: if the fan-out
    # ever regresses to `shutil.which`, these tests keep passing and the
    # dedicated hostile-PATH test is the one that fails.
    import sys as _sys

    saved = _sys.executable
    _sys.executable = str(shim_dir / "scitex-dev")
    try:
        result = runner.invoke(
            main,
            ["ecosystem", "audit-all", "--no-version-check", *cli_args],
            env=_shim_env(shim_dir),
            catch_exceptions=False,
        )
    finally:
        _sys.executable = saved
    return log, result


def _argvs_by_auditor(log: Path) -> dict[str, list[str]]:
    """Parse the shim's log into ``{auditor_name: argv_list}``."""
    out: dict[str, list[str]] = {}
    for ln in log.read_text().splitlines():
        argv = ln.split()
        # The shim now receives `-m scitex_dev ecosystem audit-<name> ...`;
        # strip the module-execution prefix before keying on the verb.
        if argv[:2] == ["-m", "scitex_dev"]:
            argv = argv[2:]
        if len(argv) >= 2 and argv[0] == "ecosystem":
            out[argv[1]] = argv
    return out


def test_audit_all_with_path_exits_zero(runner, tmp_path):
    """The shim returns 0 for every audit AND prints framing, so the
    dispatcher has something to have inspected; it must exit 0.

    Both halves are load-bearing now. Exit 0 over zero inspected lines is
    no longer a pass — it is NO VERDICT — so this asserts a clean run, not
    merely a quiet one.
    """
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


def test_audit_all_with_path_threads_to_audit_cli(runner, tmp_path):
    """audit-cli must now receive --path (path-aware follow-up)."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" in _argvs_by_auditor(log).get("audit-cli", [])


def test_audit_all_with_path_threads_to_audit_mcp_tools(runner, tmp_path):
    """audit-mcp-tools must now receive --path (path-aware follow-up)."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" in _argvs_by_auditor(log).get("audit-mcp-tools", [])


def test_audit_all_with_path_threads_to_audit_skills(runner, tmp_path):
    """audit-skills must now receive --path (path-aware follow-up)."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    # Assert
    assert "--path" in _argvs_by_auditor(log).get("audit-skills", [])


def test_audit_all_with_path_threads_to_all_six_subauditors(runner, tmp_path):
    """The proof: EVERY one of the six sub-auditors receives --path."""
    # Arrange
    repo = tmp_path / "wt"
    repo.mkdir()
    six = {
        "audit-cli",
        "audit-mcp-tools",
        "audit-skills",
        "audit-python-apis",
        "audit-project",
        "audit-django",
    }
    # Act
    log, _ = _run_with_path(runner, tmp_path, "--path", str(repo), "scitex-io")
    argvs = _argvs_by_auditor(log)
    # Assert — all six saw --path (none silently graded another tree)
    assert {a for a in six if "--path" in argvs.get(a, [])} == six


def test_audit_all_without_path_does_not_pass_path_arg(runner, tmp_path):
    """When --path is omitted, no sub-auditor argv contains --path."""
    # Arrange — only `scitex-io` is passed; no --path
    # Act
    log, _ = _run_with_path(runner, tmp_path, "scitex-io")
    # Assert
    assert not any("--path" in argv for argv in _argvs_by_auditor(log).values())
