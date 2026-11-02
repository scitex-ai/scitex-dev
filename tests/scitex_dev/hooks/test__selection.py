"""Owned native configs and real stdin bridge prove exact rule selection."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from scitex_dev.hooks._dispatch import dispatch
from scitex_dev.hooks._install_provider import install_provider

_RULES = ["dev.five-interface-commit", "dev.five-interface-changed-source"]


def _run(args, *, payload=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[3] / "src")
    env["SCITEX_DEV_NO_DRIFT_WARN"] = "1"
    env["SCITEX_LOGGING_FORCE_COLOR"] = "0"
    return subprocess.run(
        args,
        input=json.dumps(payload) if payload is not None else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def _repo(root, *, bad=False):
    repo = root / "source"
    source = repo / "src" / "example"
    source.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("""[project]
name = "example"
version = "1.0.0"
[project.scripts]
example = "example:echo"
[project.entry-points."scitex.apis"]
example = "example:plugin"
[project.entry-points."scitex_dev.skills"]
example = "example"
""")
    (source / "__init__.py").write_text(
        'def echo(value):\n    return value\n__all__ = ["echo"]\nplugin = object()\n'
    )
    (source / "_mcp_server.py").write_text(
        'from fastmcp import FastMCP\nmcp = FastMCP("example")\n@mcp.tool()\ndef echo(value):\n    return str(value)\n'
    )
    skills = source / "_skills" / "example"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "# Example\n\nUse echo(value) to return your supplied value through the package interface.\n"
    )
    if bad:
        metadata = repo / "pyproject.toml"
        metadata.write_text(
            metadata.read_text().replace("example:plugin", "example:missing")
        )
    subprocess.run(
        ["git", "-C", str(repo), "init", "--quiet"], check=True, capture_output=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    return repo


@pytest.mark.parametrize(
    "rule_ids",
    [
        [],
        (),
        "dev.five-interface-commit",
        [""],
        ["missing"],
        ["scitex-logging.output-policy"],
        ["dev.five-interface-commit", "dev.five-interface-commit"],
        ["dev.force-flag"],
    ],
)
def test_invalid_or_unbound_rule_selection_cannot_install(tmp_path, rule_ids):
    """Unknown/foreign/duplicate/empty/legacy unbound IDs fail before writing."""
    # Arrange
    target = tmp_path / "native.json"
    # Act
    # Assert
    with pytest.raises(ValueError):
        install_provider(target, provider="scitex-dev", rule_ids=rule_ids)


def test_whole_provider_default_stays_strict(tmp_path):
    """Omitting a subset must not pretend legacy implemented-in rules execute."""
    # Arrange
    target = tmp_path / "native.json"
    # Act
    # Assert
    with pytest.raises(ValueError, match="executable check"):
        install_provider(target, provider="scitex-dev")


@pytest.mark.parametrize(
    "rule_ids",
    [
        [],
        ["missing"],
        ["scitex-logging.output-policy"],
        ["dev.five-interface-commit", "dev.five-interface-commit"],
    ],
)
def test_runtime_dispatch_rejects_invalid_exact_selection(rule_ids):
    """The runtime cannot ignore a corrupted installed selection."""
    # Arrange
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
    }
    # Act
    findings = dispatch(payload, provider="scitex-dev", rule_ids=rule_ids)
    # Assert
    assert len(findings) == 1 and "Invalid hook rule selection" in findings[0]


def test_subset_install_preserves_other_selection_and_foreign_config(tmp_path):
    """Replacing an interpreter for one exact subset leaves other bindings intact."""
    # Arrange
    target = tmp_path / "native.json"
    target.write_text(
        json.dumps(
            {
                "permissions": {"allow": ["Read"]},
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Read",
                            "hooks": [
                                {"type": "command", "command": "foreign-command"}
                            ],
                        }
                    ]
                },
            }
        )
    )
    install_provider(
        target, provider="scitex-dev", rule_ids=[_RULES[0]], python="/old/interpreter"
    )
    install_provider(
        target,
        provider="scitex-dev",
        rule_ids=[_RULES[1]],
        python="/unselected/interpreter",
    )
    # Act
    install_provider(
        target, provider="scitex-dev", rule_ids=[_RULES[0]], python="/new/interpreter"
    )
    config = json.loads(target.read_text())
    commands = [
        hook["command"]
        for entries in config["hooks"].values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    observed = (
        config["permissions"],
        len(commands),
        "foreign-command" in commands,
        sum("/new/interpreter" in command for command in commands),
        sum("/unselected/interpreter" in command for command in commands),
        any("/old/interpreter" in command for command in commands),
    )
    # Assert
    assert observed == ({"allow": ["Read"]}, 3, True, 1, 1, False)


@pytest.mark.parametrize("bad,expected", [(False, 0), (True, 2)])
def test_installed_exact_command_drives_real_stdin_bridge(tmp_path, bad, expected):
    """A generated native command grades real staged valid/bad source bytes."""
    # Arrange
    repo = _repo(tmp_path, bad=bad)
    target = tmp_path / "native.json"
    install_provider(target, provider="scitex-dev", rule_ids=_RULES)
    config = json.loads(target.read_text())
    command = config["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    payload = {
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": f"git -C {shlex.quote(str(repo))} commit -m fixture"},
    }
    # Act
    result = _run(shlex.split(command), payload=payload)
    words = shlex.split(command)
    selected = [
        words[index + 1] for index, word in enumerate(words) if word == "--rule"
    ]
    # Assert
    assert (
        result.returncode,
        result.stdout,
        sorted(selected),
        "PS-IF-004" in result.stderr,
    ) == (expected, "", sorted(_RULES), bad)


def test_real_install_cli_carries_repeatable_rule_ids(tmp_path):
    """The public CLI option performs the same actual config installation."""
    # Arrange
    target = tmp_path / "native.json"
    args = [
        sys.executable,
        "-m",
        "scitex_dev",
        "hooks",
        "install",
        "--provider",
        "scitex-dev",
        "--config",
        str(target),
        "--rule",
        _RULES[0],
        "--rule",
        _RULES[1],
    ]
    # Act
    result = _run(args)
    config = json.loads(target.read_text()) if target.exists() else {}
    commands = [
        hook["command"]
        for entries in config.get("hooks", {}).values()
        for entry in entries
        for hook in entry["hooks"]
    ]
    # Assert
    assert (
        result.returncode,
        len(commands),
        all(all(rule in command for rule in _RULES) for command in commands),
    ) == (0, 2, True)
