"""Exercise the bundled lint handler's shell/argv contract with owned tools.

The executable fixture records argv and returns a selected process exit status;
real ESLint parser/rule and whole-hook qualification are separate integration
checks, not simulated by this fixture.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from scitex_dev._hooks import run_lint_sh_path

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="Bash hook")


def _invoke(
    tmp_path, configurations, exit_code=0, available=True, relative=False, legacy=False
):
    project = tmp_path / "project with spaces"
    source = project / "src/ui/probe.ts"
    source.parent.mkdir(parents=True)
    source.write_text("export const ownedValue = 1;\n")
    for name in configurations:
        config = project / name
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("{}\n")
    tools = tmp_path / "tools"
    tools.mkdir()
    captured = tmp_path / "argv"
    captured_cwd = tmp_path / "child-cwd"
    if available:
        executable = tools / "eslint"
        executable.write_text(
            '#!/bin/sh\nprintf "%s\\0" "$@" > "$OWNED_ESLINT_CAPTURE"\n'
            'pwd -P > "$OWNED_ESLINT_CWD"\nexit "$OWNED_ESLINT_EXIT"\n'
        )
        executable.chmod(0o755)
    hook = Path(run_lint_sh_path()).read_text()
    handler = (
        "lint_js_ts() {"
        + hook.split("lint_js_ts() {", 1)[1].split("\n}\n", 1)[0]
        + "\n}\n"
    )
    elsewhere = tmp_path / "unrelated working directory"
    elsewhere.mkdir()
    result = subprocess.run(
        [
            shutil.which("bash"),
            "-c",
            handler + '\nlint_js_ts "$1"',
            "owned-hook",
            str(source.relative_to(project)) if relative else str(source),
        ],
        cwd=project if relative else elsewhere,
        env={
            "HOME": str(tmp_path / "owned-home"),
            "LANG": "C.UTF-8",
            "PATH": str(tools) + (os.pathsep + os.defpath if available else ""),
            "OWNED_ESLINT_CAPTURE": str(captured),
            "OWNED_ESLINT_EXIT": str(exit_code),
            "OWNED_ESLINT_CWD": str(captured_cwd),
            "ESLINT_USE_FLAT_CONFIG": "false" if legacy else "true",
        },
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    argv = (
        captured.read_bytes().decode().split("\0")[:-1] if captured.exists() else None
    )
    return (
        project,
        source,
        result.returncode,
        argv,
        captured_cwd.read_text().strip() if captured_cwd.exists() else None,
    )


@pytest.mark.parametrize(
    ("configurations", "selected", "child_exit"),
    [
        ([], None, 0),
        ([".eslintrc.json"], None, 0),
        (["eslint.config.mjs"], "eslint.config.mjs", 0),
        (
            ["eslint.config.mjs", "src/ui/eslint.config.mjs"],
            "src/ui/eslint.config.mjs",
            0,
        ),
        (["src/eslint.config.mjs"], "src/eslint.config.mjs", 0),
        (
            [
                "src/ui/eslint.config.cjs",
                "src/ui/eslint.config.js",
                "src/ui/eslint.config.mjs",
            ],
            "src/ui/eslint.config.js",
            0,
        ),
        (["src/ui/eslint.config.ts"], "src/ui/eslint.config.ts", 0),
        (["src/ui/eslint.config.mts"], "src/ui/eslint.config.mts", 0),
        (["src/ui/eslint.config.cts"], "src/ui/eslint.config.cts", 0),
        (["src/ui/eslint.config.mjs"], "src/ui/eslint.config.mjs", 1),
        (["src/ui/eslint.config.mjs"], "src/ui/eslint.config.mjs", 2),
    ],
)
def test_js_handler_selects_nearest_config_and_preserves_exit(
    tmp_path, configurations, selected, child_exit
):
    # Arrange
    expected_prefix = (
        ["--config", str(tmp_path / "project with spaces" / selected)]
        if selected
        else []
    )
    # Act
    _, source, actual_exit, argv, child_cwd = _invoke(
        tmp_path, configurations, child_exit
    )
    # Assert
    assert (actual_exit, argv, child_cwd) == (
        child_exit,
        expected_prefix + ["--fix", str(source)],
        str((tmp_path / "project with spaces" / selected).parent)
        if selected
        else str(tmp_path / "unrelated working directory"),
    )


def test_js_handler_keeps_missing_executable_behavior(tmp_path):
    # Arrange
    configurations = ["src/ui/eslint.config.mjs"]
    # Act
    _, _, actual_exit, argv, _ = _invoke(tmp_path, configurations, available=False)
    # Assert
    assert (actual_exit, argv) == (0, None)


def test_js_handler_normalizes_relative_file_before_chdir(tmp_path):
    # Arrange
    selected = "src/ui/eslint.config.mjs"
    # Act
    project, source, actual_exit, argv, child_cwd = _invoke(
        tmp_path, [selected], relative=True
    )
    # Assert
    assert (actual_exit, argv, child_cwd) == (
        0,
        ["--config", str(project / selected), "--fix", str(source)],
        str((project / selected).parent),
    )


def test_js_handler_respects_explicit_legacy_mode(tmp_path):
    # Arrange
    configurations = ["src/ui/eslint.config.mjs", ".eslintrc.json"]
    # Act
    _, source, actual_exit, argv, child_cwd = _invoke(
        tmp_path, configurations, legacy=True
    )
    # Assert
    assert (actual_exit, argv, child_cwd) == (
        0,
        ["--fix", str(source)],
        str(tmp_path / "unrelated working directory"),
    )
