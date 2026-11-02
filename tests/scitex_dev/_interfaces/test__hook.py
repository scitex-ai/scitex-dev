"""Real Git worktrees exercise the same source checks at hook boundaries."""

from __future__ import annotations

import subprocess

import pytest

from scitex_dev._interfaces._hook import _commit_repo, check_payload
from scitex_dev._interfaces._project import inspect_interfaces


@pytest.fixture
def git_package(package):
    """Stage real interface source without committing or invoking host hooks."""
    subprocess.run(
        ["git", "-C", str(package), "init", "--quiet"], capture_output=True, check=True
    )
    subprocess.run(
        ["git", "-C", str(package), "add", "."], capture_output=True, check=True
    )
    return package


def _commit(root):
    return {
        "cwd": str(root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": f'git -C "{root}" commit -m contract'},
    }


def test_commit_hook_and_project_checker_report_identical_error(git_package):
    """A real missing Web binding has the same rule/detail in both callers."""
    # Arrange
    (git_package / "src/branded_demo/web.py").unlink()
    subprocess.run(
        ["git", "-C", str(git_package), "add", "-u"], capture_output=True, check=True
    )
    # Act
    source = [f for f in inspect_interfaces(git_package) if f.severity == "E"]
    findings = check_payload(_commit(git_package))
    expected = [
        f"{item.rule}: {item.path}:{item.line}: {item.detail}" for item in source
    ]
    # Assert
    assert findings == expected and len(findings) == 1


def test_real_complete_package_commit_is_allowed(git_package):
    """The hook can stay green for implemented source without executing commit."""
    # Arrange
    # Act
    # Assert
    assert check_payload(_commit(git_package)) == []


def test_pre_edit_checks_no_old_bytes_or_unrelated_debt(git_package):
    """Pre-edit is not a false claim to inspect proposed bytes after mutation."""
    # Arrange
    (git_package / "src/branded_demo/web.py").unlink()
    payload = {
        "cwd": str(git_package),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(git_package / "notes.md"), "content": "Notes"},
    }
    # Act
    # Assert
    assert check_payload(payload) == []


def test_post_edit_interface_change_uses_new_source(git_package):
    """Changed interface metadata triggers the same pure checker after writing."""
    # Arrange
    # HEAD is a real committed tree solely to make changed-path enumeration
    # meaningful. Identity/config are per-command and cannot touch host config.
    subprocess.run(
        [
            "git",
            "-C",
            str(git_package),
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        capture_output=True,
        check=True,
    )
    metadata = git_package / "pyproject.toml"
    metadata.write_text(
        metadata.read_text().replace(
            'demo = "branded_demo.web:plugin"', 'demo = "branded_demo.web:missing"'
        )
    )
    payload = {
        "cwd": str(git_package),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": str(metadata)},
    }
    # Act
    # Assert
    assert any("PS-IF-004" in item for item in check_payload(payload))


@pytest.mark.parametrize(
    "command",
    [
        "echo git commit",
        "printf '%s' 'git commit'",
        "git status",
        "python -c 'pass'",
        "git log --format=commit",
    ],
)
def test_non_commit_shell_text_is_not_a_commit_gate(command, tmp_path):
    """Mentioning git/commit in output or arguments must not trigger the gate."""
    # Arrange
    # Act
    # Assert
    assert _commit_repo(command, tmp_path) is None


@pytest.mark.parametrize(
    "command",
    [
        'git -C "target space" commit -m x',
        'cd "target space" && git commit -m x',
        'git -c commit.gpgsign=false -C "target space" commit -m x',
    ],
)
def test_commit_target_is_resolved_without_running_shell(command, tmp_path):
    """Ordinary explicit git and cd+git forms preserve their actual target."""
    # Arrange
    # Act
    # Assert
    assert _commit_repo(command, tmp_path) == (tmp_path / "target space").resolve()


def test_declared_hooks_bind_the_same_executable_checker():
    """Normal leaf provider declarations include actual callable bindings."""
    # Arrange
    from scitex_dev._hook_rules import provide

    # Act
    rules = [r for r in provide() if r.id.startswith("dev.five-interface-")]
    observed = sorted((r.event, r.check) for r in rules)
    # Assert
    assert observed == [
        ("post-tool-use", "scitex_dev._interfaces._hook:check_payload"),
        ("pre-tool-use", "scitex_dev._interfaces._hook:check_payload"),
    ]


def test_unstaged_good_source_cannot_conceal_bad_index(git_package):
    """The pre-commit gate grades committed bytes, not a corrected working copy."""
    # Arrange
    metadata = git_package / "pyproject.toml"
    good = metadata.read_text()
    metadata.write_text(
        good.replace("branded_demo.web:plugin", "branded_demo.web:missing")
    )
    subprocess.run(
        ["git", "-C", str(git_package), "add", "pyproject.toml"],
        capture_output=True,
        check=True,
    )
    metadata.write_text(good)
    # Act
    observed = (
        inspect_interfaces(git_package),
        any("PS-IF-004" in f for f in check_payload(_commit(git_package))),
    )
    # Assert
    assert observed == ([], True)


def test_unstaged_bad_source_does_not_fabricate_a_bad_commit(git_package):
    """The reverse control demonstrates that the index is the intended boundary."""
    # Arrange
    metadata = git_package / "pyproject.toml"
    metadata.write_text(
        metadata.read_text().replace(
            "branded_demo.web:plugin", "branded_demo.web:missing"
        )
    )
    # Act
    observed = (
        any(f.rule == "PS-IF-004" for f in inspect_interfaces(git_package)),
        check_payload(_commit(git_package)),
    )
    # Assert
    assert observed == (True, [])


def test_staged_source_symlink_cannot_use_good_working_copy(git_package):
    """Git symlink mode is refused even when an unstaged regular file looks good."""
    # Arrange
    path = git_package / "src/branded_demo/web.py"
    good = path.read_text()
    path.unlink()
    path.symlink_to("/private/foreign-source.py")
    subprocess.run(
        ["git", "-C", str(git_package), "add", str(path)],
        capture_output=True,
        check=True,
    )
    path.unlink()
    path.write_text(good)
    # Act
    observed = (
        inspect_interfaces(git_package),
        any("PS-IF-004" in f for f in check_payload(_commit(git_package))),
    )
    # Assert
    assert observed == ([], True)
