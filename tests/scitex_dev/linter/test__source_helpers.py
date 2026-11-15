"""Real project configuration and CLI controls for root library directories."""

import os
import subprocess
import sys

import pytest

from scitex_dev.linter._source_helpers import is_script
from scitex_dev.linter.config import LinterConfig, load_config


def _project(root, section="tool.scitex-dev.linter"):
    root.mkdir()
    (root / "pyproject.toml").write_text(
        f'[{section}]\nlibrary_dirs = ["."]\n'
    )
    return root


@pytest.mark.parametrize("section", ["tool.scitex-dev.linter", "tool.scitex-linter"])
@pytest.mark.parametrize("relative", ["worker.py", "nested/worker.py"])
def test_root_library_is_relative_to_its_config_file(tmp_path, section, relative):
    # Arrange
    root = _project(tmp_path / "project", section)
    file = root / relative
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("VALUE = 1\n")
    config = load_config(str(file))
    # Act
    script = is_script(str(file), config)
    # Assert
    assert script is False


def _cli_check(tmp_path, section, target):
    root = _project(tmp_path / "project", section)
    library = root / "worker.py"
    library.write_text("VALUE = 1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "pyproject.toml").write_text(
        '[tool.scitex-dev.linter]\nlibrary_dirs = ["lib"]\n'
    )
    script = outside / "worker.py"
    script.write_text("VALUE = 1\n")
    command = [
        sys.executable, "-c",
        "import sys; from scitex_dev.linter.cli import main; sys.exit(main())",
        "validate-files",
    ]
    return subprocess.run(
        [*command, str({"library": library, "script": script}[target]),
         "--severity", "error", "--no-color"],
        cwd=outside, capture_output=True, text=True, timeout=30,
    )


@pytest.mark.parametrize("section", ["tool.scitex-dev.linter", "tool.scitex-linter"])
def test_cli_accepts_root_library(tmp_path, section):
    # Arrange
    # Act
    accepted = _cli_check(tmp_path, section, "library")
    # Assert
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr


@pytest.mark.parametrize("section", ["tool.scitex-dev.linter", "tool.scitex-linter"])
def test_cli_root_library_has_no_missing_guard_finding(tmp_path, section):
    # Arrange
    # Act
    accepted = _cli_check(tmp_path, section, "library")
    # Assert
    assert "STX-S002" not in accepted.stdout


@pytest.mark.parametrize("section", ["tool.scitex-dev.linter", "tool.scitex-linter"])
def test_cli_refuses_unconfigured_script(tmp_path, section):
    # Arrange
    # Act
    refused = _cli_check(tmp_path, section, "script")
    # Assert
    assert refused.returncode == 2, refused.stdout + refused.stderr


@pytest.mark.parametrize("section", ["tool.scitex-dev.linter", "tool.scitex-linter"])
def test_cli_unconfigured_script_keeps_missing_guard_finding(tmp_path, section):
    # Arrange
    # Act
    refused = _cli_check(tmp_path, section, "script")
    # Assert
    assert "STX-S002" in refused.stdout


def _outside_project(tmp_path):
    root = _project(tmp_path / "project")
    outside = tmp_path / "project-other"
    outside.mkdir()
    file = outside / "worker.py"
    file.write_text("VALUE = 1\n")
    return root, file, load_config(str(root))


def test_loaded_root_library_does_not_exempt_a_sibling(tmp_path):
    # Arrange
    root, file, config = _outside_project(tmp_path)
    # Act
    script = is_script(str(file), config)
    # Assert
    assert script is True


def test_loaded_root_library_does_not_exempt_an_external_symlink_target(tmp_path):
    # Arrange
    root, file, config = _outside_project(tmp_path)
    link = root / "worker.py"
    link.symlink_to(file)
    # Act
    script = is_script(str(link), config)
    # Assert
    assert script is True


def test_root_library_marker_does_not_disable_rules(tmp_path):
    # Arrange
    root = _project(tmp_path / "project")
    # Act
    config = load_config(str(root))
    # Assert
    assert config.disable == []


@pytest.mark.parametrize("directory, expected", [("lib", False), ("", True)])
def test_named_library_and_empty_entry_keep_their_meaning(tmp_path, directory, expected):
    # Arrange
    file = tmp_path / "lib" / "worker.py"
    file.parent.mkdir()
    file.write_text("VALUE = 1\n")
    config = LinterConfig(library_dirs=[directory])
    # Act
    script = is_script(str(file), config)
    # Assert
    assert script is expected


def test_programmatic_dot_uses_current_directory_without_exempting_a_sibling(tmp_path):
    # Arrange
    root = tmp_path / "project"
    root.mkdir()
    file = root / "worker.py"
    file.write_text("VALUE = 1\n")
    outside = tmp_path / "worker.py"
    outside.write_text("VALUE = 1\n")
    config = LinterConfig(library_dirs=["."])
    previous = os.getcwd()
    # Act
    try:
        os.chdir(root)
        classifications = [is_script(str(path), config) for path in (file, outside)]
    finally:
        os.chdir(previous)
    # Assert
    assert classifications == [False, True]
