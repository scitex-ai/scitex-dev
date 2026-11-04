"""Configuration behavior, including executable source-owned skill examples."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from scitex_dev._core.config import DevConfig, load_config

_GUIDE = (
    Path(__file__).resolve().parents[3]
    / "src/scitex_dev/_skills/scitex-dev/12_config.md"
)


@pytest.fixture
def isolated_skill_config(tmp_path):
    overrides = {
        "SCITEX_DIR": str(tmp_path / "scitex"),
        "SCITEX_DEV_CONFIG": str(tmp_path / "config.yaml"),
        "SCITEX_DEV_KNOB_STATE": str(tmp_path / "knobs.json"),
    }
    before = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    try:
        yield tmp_path
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _documented_yaml():
    return re.search(r"```yaml\n(.*?)```", _GUIDE.read_text(), re.DOTALL).group(1)


def test_documented_opt_out_preserves_registered_package_metadata(
    isolated_skill_config,
):
    path = isolated_skill_config / "config.yaml"
    path.write_text("")
    original = next(p for p in load_config().packages if p.name == "scitex-writer")
    path.write_text(_documented_yaml())
    updated = next(p for p in load_config().packages if p.name == "scitex-writer")
    assert not updated.skills_enabled and updated.mcp_enabled
    for field in ("local_path", "pypi_name", "github_repo", "import_name"):
        assert getattr(updated, field) == getattr(original, field), field


def test_documented_switches_match_cli_and_cli_overrides_preserve_yaml(
    isolated_skill_config,
):
    from scitex_dev._cli._root import main

    path = isolated_skill_config / "config.yaml"
    path.write_text(_documented_yaml())
    original = path.read_bytes()
    runner = CliRunner()
    for args, expected in [
        (["dev", "skills", "status", "--json"], False),
        (["mcp", "status", "--json"], True),
    ]:
        result = runner.invoke(main, args)
        assert result.exit_code == 0, result.output
        assert json.loads(result.output)["scitex-writer"] is expected
    for args in [
        ["dev", "skills", "enable", "scitex-writer", "--yes"],
        ["mcp", "disable", "scitex-writer", "--yes"],
    ]:
        result = runner.invoke(main, args)
        assert result.exit_code == 0, result.output
    package = next(p for p in load_config().packages if p.name == "scitex-writer")
    assert package.skills_enabled and not package.mcp_enabled
    assert path.read_bytes() == original


def test_configuration_skill_python_examples_execute_in_isolated_environment(
    isolated_skill_config,
):
    (isolated_skill_config / "config.yaml").write_text(_documented_yaml())
    blocks = re.findall(r"```python\n(.*?)```", _GUIDE.read_text(), re.DOTALL)
    assert blocks, "The configuration skill must retain an executable Python example"
    for block in blocks:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                block
                + '\nimport json,sys\nsys.stdout.write(json.dumps({"path":str(selected_file),"skills":skill_switches["scitex-writer"],"mcp":mcp_switches["scitex-writer"]}))',
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        actual = json.loads(result.stdout)
        assert actual == {
            "path": str(isolated_skill_config / "config.yaml"),
            "skills": False,
            "mcp": True,
        }


def test_dev_config_defaults_to_three_freshness_days():
    # Arrange
    config = DevConfig()
    # Act
    days = config.freshness.freshness_days
    # Assert
    assert days == 3


def test_dev_config_defaults_to_scitex_ai_organization():
    # Arrange
    config = DevConfig()
    # Act
    organization = config.freshness.organization
    # Assert
    assert organization == "scitex-ai"


def test_load_config_accepts_freshness_override(tmp_path):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text(
        "freshness:\n"
        "  organization: other-org\n"
        "  freshness_days: 7\n"
        "  cards: required\n"
    )
    # Act
    loaded = load_config(config)
    actual = (
        loaded.freshness.organization,
        loaded.freshness.freshness_days,
        loaded.freshness.cards,
    )
    # Assert
    assert actual == ("other-org", 7, "required")
