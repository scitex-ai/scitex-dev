"""Actual Git child isolation between two disposable repositories.

These controls construct a hook-local environment; they do not reconstruct
the unrecorded historical Writer child environment or run its selected tests.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scitex_dev._hooks import HOOK_DIR

HOOKS = Path(HOOK_DIR)
SHIM = HOOKS / "_git_local_env.sh"
WRAPPER = HOOKS / "run_testmon.sh"
FIXTURE_CHILD = """from pathlib import Path
import os
import subprocess
import sys

target = Path(sys.argv[1])
def git(*args):
    subprocess.run(['git', '-C', str(target), *args], check=True,
                   capture_output=True, text=True, timeout=3)
git('init', '-q')
git('config', 'user.name', 'Fixture Tester')
git('config', 'user.email', 'fixture@example.test')
payload = target / 'fixture.txt'
payload.write_text('disposable fixture payload\\n')
git('add', 'fixture.txt')
git('commit', '-qm', 'fixture commit')
git('config', 'core.bare', 'true')
"""


def _env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    return {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _git(repo, env, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    ).stdout.strip()


def _snapshot(repo, env):
    return {
        "head": _git(repo, env, "rev-parse", "HEAD"),
        "config": (repo / ".git" / "config").read_bytes(),
        "index": hashlib.sha256((repo / ".git" / "index").read_bytes()).hexdigest(),
    }


@pytest.fixture
def repositories(tmp_path):
    env = _env(tmp_path)
    delivery = tmp_path / "delivery"
    foreign = tmp_path / "foreign"
    delivery.mkdir()
    foreign.mkdir()
    _git(delivery, env, "init", "-q")
    _git(delivery, env, "config", "user.name", "Delivery Owner")
    _git(delivery, env, "config", "user.email", "owner@example.test")
    (delivery / "owned.txt").write_text("delivery source stays intact\n")
    _git(delivery, env, "add", "owned.txt")
    _git(delivery, env, "commit", "-qm", "delivery baseline")
    child = tmp_path / "fixture_child.py"
    child.write_text(FIXTURE_CHILD)
    inherited = dict(
        env,
        GIT_DIR=str(delivery / ".git"),
        GIT_INDEX_FILE=str(delivery / ".git" / "index"),
    )
    return delivery, foreign, child, env, inherited


def _fixture_run(repositories, *, isolated):
    delivery, foreign, child, _, inherited = repositories
    argv = [sys.executable, "-I", "-B", str(child), str(foreign)]
    if isolated:
        argv = ["bash", str(SHIM), *argv]
    return subprocess.run(
        argv,
        cwd=delivery,
        env=inherited,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_unisolated_foreign_fixture_changes_delivery_head(repositories):
    # Arrange
    delivery, _, _, env, _ = repositories
    before = _snapshot(delivery, env)
    # Act
    result = _fixture_run(repositories, isolated=False)
    observed = (result.returncode, _snapshot(delivery, env)["head"] != before["head"])
    # Assert
    assert observed == (0, True)


def test_unisolated_foreign_fixture_changes_delivery_config(repositories):
    # Arrange
    delivery, _, _, env, _ = repositories
    # Act
    result = _fixture_run(repositories, isolated=False)
    observed = (
        result.returncode,
        _git(delivery, env, "config", "user.name"),
        _git(delivery, env, "config", "core.bare"),
    )
    # Assert
    assert observed == (0, "Fixture Tester", "true")


def test_unisolated_foreign_fixture_changes_delivery_index(repositories):
    # Arrange
    delivery, _, _, env, _ = repositories
    before = _snapshot(delivery, env)
    # Act
    result = _fixture_run(repositories, isolated=False)
    observed = (result.returncode, _snapshot(delivery, env)["index"] != before["index"])
    # Assert
    assert observed == (0, True)


def test_isolated_foreign_fixture_preserves_delivery_snapshot(repositories):
    # Arrange
    delivery, _, _, env, _ = repositories
    before = _snapshot(delivery, env)
    # Act
    result = _fixture_run(repositories, isolated=True)
    observed = (result.returncode, _snapshot(delivery, env))
    # Assert
    assert observed == (0, before)


def test_isolated_foreign_fixture_owns_its_commit(repositories):
    # Arrange
    _, foreign, _, env, _ = repositories
    # Act
    result = _fixture_run(repositories, isolated=True)
    observed = (result.returncode, _git(foreign, env, "log", "-1", "--format=%s"))
    # Assert
    assert observed == (0, "fixture commit")


def test_isolated_foreign_fixture_owns_its_config(repositories):
    # Arrange
    _, foreign, _, env, _ = repositories
    # Act
    result = _fixture_run(repositories, isolated=True)
    observed = (
        result.returncode,
        _git(foreign, env, "config", "user.name"),
        _git(foreign, env, "config", "core.bare"),
    )
    # Assert
    assert observed == (0, "Fixture Tester", "true")


def test_isolated_foreign_fixture_owns_its_index(repositories):
    # Arrange
    _, foreign, _, env, _ = repositories
    # Act
    result = _fixture_run(repositories, isolated=True)
    observed = (result.returncode, _git(foreign, env, "ls-files"))
    # Assert
    assert observed == (0, "fixture.txt")


def test_no_hook_environment_keeps_normal_foreign_fixture(repositories):
    # Arrange
    delivery, foreign, child, env, _ = repositories
    before = _snapshot(delivery, env)
    # Act
    result = subprocess.run(
        ["bash", str(SHIM), sys.executable, "-I", "-B", str(child), str(foreign)],
        cwd=delivery,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    observed = (
        result.returncode,
        _snapshot(delivery, env),
        _git(foreign, env, "log", "-1", "--format=%s"),
    )
    # Assert
    assert observed == (0, before, "fixture commit")


def test_child_keeps_nonlocal_selected_environment(repositories, tmp_path):
    # Arrange
    delivery, _, _, env, inherited = repositories
    inherited.update(
        SCITEX_DEV_PYTHON=sys.executable,
        SCITEX_TEST_SENTINEL="selection",
        GIT_AUTHOR_NAME="Preserved Author",
    )
    expected = (env["HOME"], sys.executable, "selection", "Preserved Author")
    report = tmp_path / "child_environment.txt"
    program = "import os,sys;open(sys.argv[1],'w').write(repr(tuple(os.environ[k] for k in ('HOME','SCITEX_DEV_PYTHON','SCITEX_TEST_SENTINEL','GIT_AUTHOR_NAME'))))"
    # Act
    result = subprocess.run(
        ["bash", str(SHIM), sys.executable, "-I", "-B", "-c", program, str(report)],
        cwd=delivery,
        env=inherited,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    observed = (result.returncode, report.read_text())
    # Assert
    assert observed == (0, repr(expected))


def test_child_removes_only_canonical_local_names(repositories, tmp_path):
    # Arrange
    delivery, _, _, _, inherited = repositories
    inherited.update(
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0="core.hooksPath",
        GIT_CONFIG_VALUE_0=str(tmp_path / "no-hooks"),
        GIT_NOT_REPOSITORY_LOCAL="keep",
    )
    report = tmp_path / "local_environment.txt"
    program = "import os,sys;open(sys.argv[1],'w').write(repr(('GIT_DIR' in os.environ,'GIT_INDEX_FILE' in os.environ,'GIT_CONFIG_COUNT' in os.environ,os.environ.get('GIT_CONFIG_KEY_0'),os.environ.get('GIT_NOT_REPOSITORY_LOCAL'))))"
    # Act
    result = subprocess.run(
        ["bash", str(SHIM), sys.executable, "-I", "-B", "-c", program, str(report)],
        cwd=delivery,
        env=inherited,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    observed = (result.returncode, report.read_text())
    # Assert
    assert observed == (0, repr((False, False, False, "core.hooksPath", "keep")))


def test_child_exit_code_is_preserved(tmp_path):
    # Arrange
    env = _env(tmp_path)
    # Act
    result = subprocess.run(
        ["bash", str(SHIM), sys.executable, "-I", "-B", "-c", "raise SystemExit(9)"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    # Assert
    assert result.returncode == 9


def test_missing_git_refuses_before_child(tmp_path):
    # Arrange
    env = _env(tmp_path)
    env["PATH"] = str(tmp_path / "empty-bin")
    marker = tmp_path / "not-created"
    # Act
    result = subprocess.run(
        [
            "/bin/bash",
            str(SHIM),
            sys.executable,
            "-I",
            "-B",
            "-c",
            "from pathlib import Path;import sys;Path(sys.argv[1]).touch()",
            str(marker),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    observed = (result.returncode, marker.exists())
    # Assert
    assert observed == (2, False)


def test_missing_child_command_refuses(tmp_path):
    # Arrange
    env = _env(tmp_path)
    # Act
    result = subprocess.run(
        ["bash", str(SHIM)],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    # Assert
    assert result.returncode == 2
