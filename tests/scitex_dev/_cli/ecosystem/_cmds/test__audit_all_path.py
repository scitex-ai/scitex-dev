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

PA-306 no-mocks: we exercise the real Click command + the real
subprocess fan-out. To make the fan-out observable we shim
``scitex-dev`` on PATH with a tiny real script that just records its
argv to a file — real process, real argv parsing, just a stub binary
that's the test's own code on disk.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# audit-project / audit-django / audit-python-apis: --path is a legal alias
# of --repo (Click multi-flag option). Confirm the help text mentions both.
# ---------------------------------------------------------------------------


def test_audit_project_help_advertises_path_flag(runner):
    """--path appears in audit-project --help alongside --repo."""
    from scitex_dev._cli._root import main

    result = runner.invoke(main, ["ecosystem", "audit-project", "--help"])

    assert result.exit_code == 0
    assert "--path" in result.output
    assert "--repo" in result.output


def test_audit_django_help_advertises_path_flag(runner):
    """--path appears in audit-django --help alongside --repo."""
    from scitex_dev._cli._root import main

    result = runner.invoke(main, ["ecosystem", "audit-django", "--help"])

    assert result.exit_code == 0
    assert "--path" in result.output
    assert "--repo" in result.output


def test_audit_python_apis_help_advertises_path_flag(runner):
    """--path appears in audit-python-apis --help alongside --repo."""
    from scitex_dev._cli._root import main

    result = runner.invoke(main, ["ecosystem", "audit-python-apis", "--help"])

    assert result.exit_code == 0
    assert "--path" in result.output
    assert "--repo" in result.output


# ---------------------------------------------------------------------------
# audit-all --path: thread-through fan-out. PATH-shim a fake `scitex-dev`
# that records every argv it sees; assert the path-aware auditors got
# --path, the others didn't.
# ---------------------------------------------------------------------------


def test_audit_all_help_advertises_path_flag(runner):
    """--path appears in audit-all --help."""
    from scitex_dev._cli._root import main

    result = runner.invoke(main, ["ecosystem", "audit-all", "--help"])

    assert result.exit_code == 0
    assert "--path" in result.output
    assert "worktree" in result.output


def test_audit_all_path_requires_single_distribution(runner, tmp_path):
    """audit-all --path /some/path scitex-io scitex-stats → exit 2."""
    from scitex_dev._cli._root import main

    repo = tmp_path / "fake-checkout"
    repo.mkdir()

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

    assert result.exit_code == 2
    assert "--path requires exactly ONE distribution" in result.output


def _install_shim(shim_dir: Path, log: Path) -> Path:
    """Drop a real `scitex-dev` script that just records its argv to ``log``.

    The shim is a posix shell script (works on every CI runner the matrix
    uses) that writes one TAB-separated argv per line. audit-all calls
    ``scitex-dev ecosystem <auditor> <dist> [--path PATH] ...`` — the
    shim captures every such invocation so the test can introspect what
    flags actually got passed.
    """
    script = shim_dir / "scitex-dev"
    script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\nexit 0\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def test_audit_all_path_threaded_through_to_project_django_python_apis(
    runner, tmp_path, monkeypatch
):
    """--path PATH gets appended to project/django/python-apis (not cli/mcp/skills)."""
    from scitex_dev._cli._root import main

    # Arrange — real repo path, real shim binary on PATH.
    repo = tmp_path / "wt"
    repo.mkdir()
    log = tmp_path / "argv.log"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    _install_shim(shim_dir, log)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")
    # Bypass the version-check that would shell out before our shim.
    # (The version check uses scitex-dev too; --no-version-check turns it off.)

    # Act
    result = runner.invoke(
        main,
        [
            "ecosystem",
            "audit-all",
            "--no-version-check",
            "--path",
            str(repo),
            "scitex-io",
        ],
    )

    # Assert — overall exit 0 because every shim invocation returned 0.
    assert result.exit_code == 0, (result.output, log.read_text() if log.exists() else "")

    # Parse the shim's log.
    lines = [ln for ln in log.read_text().splitlines() if ln.strip()]
    # Each line is the joined argv: `ecosystem audit-<X> scitex-io [--path REPO] [...]`
    cmds = [ln.split() for ln in lines]

    # Group by auditor name (index 1 after `ecosystem`).
    by_audit: dict[str, list[str]] = {}
    for argv in cmds:
        if len(argv) >= 2 and argv[0] == "ecosystem":
            by_audit[argv[1]] = argv

    # Path-aware auditors MUST receive --path <repo>.
    for path_aware in ("audit-project", "audit-django", "audit-python-apis"):
        argv = by_audit.get(path_aware)
        assert argv is not None, (
            f"{path_aware} was not invoked; log:\n{log.read_text()}"
        )
        assert "--path" in argv, f"--path missing from {path_aware} argv: {argv}"
        i = argv.index("--path")
        assert argv[i + 1] == str(repo), (
            f"--path argument for {path_aware} should be {repo!s}, "
            f"got {argv[i + 1]!r}"
        )

    # Auditors that don't yet support --path MUST NOT receive it.
    for not_path_aware in ("audit-cli", "audit-mcp-tools", "audit-skills"):
        argv = by_audit.get(not_path_aware)
        assert argv is not None, (
            f"{not_path_aware} was not invoked; log:\n{log.read_text()}"
        )
        assert "--path" not in argv, (
            f"--path should NOT be passed to {not_path_aware} "
            f"(not path-aware yet); got: {argv}"
        )


def test_audit_all_without_path_does_not_pass_path_arg(runner, tmp_path, monkeypatch):
    """When --path is omitted, no sub-auditor gets a --path argument."""
    from scitex_dev._cli._root import main

    log = tmp_path / "argv.log"
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    _install_shim(shim_dir, log)
    monkeypatch.setenv("PATH", f"{shim_dir}{os.pathsep}{os.environ['PATH']}")

    runner.invoke(
        main,
        [
            "ecosystem",
            "audit-all",
            "--no-version-check",
            "scitex-io",
        ],
    )

    if not log.exists():
        pytest.fail("shim was never invoked")
    text = log.read_text()
    for ln in text.splitlines():
        assert "--path" not in ln, f"--path leaked into argv: {ln}"
