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
    # Arrange
    path = isolated_skill_config / "config.yaml"
    path.write_text("")
    original = next(p for p in load_config().packages if p.name == "scitex-writer")
    path.write_text(_documented_yaml())
    # Act
    updated = next(p for p in load_config().packages if p.name == "scitex-writer")
    fields = ("local_path", "pypi_name", "github_repo", "import_name")
    # Assert
    assert {f: getattr(updated, f) for f in fields} == {
        f: getattr(original, f) for f in fields
    }


@pytest.mark.parametrize(
    "args,expected",
    [
        (["dev", "skills", "status", "--json"], False),
        (["mcp", "status", "--json"], True),
    ],
)
def test_documented_switches_match_cli(isolated_skill_config, args, expected):
    # Arrange
    from scitex_dev._cli._root import main

    path = isolated_skill_config / "config.yaml"
    path.write_text(_documented_yaml())
    # Act
    result = CliRunner().invoke(main, args)
    actual = (result.exit_code, json.loads(result.output)["scitex-writer"])
    # Assert
    assert actual == (0, expected)


def test_cli_managed_switches_override_yaml_preferences(isolated_skill_config):
    # Arrange
    from scitex_dev._cli._root import main

    (isolated_skill_config / "config.yaml").write_text(_documented_yaml())
    runner, outcomes = CliRunner(), []
    # Act
    for args in [
        ["dev", "skills", "enable", "scitex-writer", "--yes"],
        ["mcp", "disable", "scitex-writer", "--yes"],
    ]:
        result = runner.invoke(main, args)
        outcomes.append(result.exit_code)
    package = next(p for p in load_config().packages if p.name == "scitex-writer")
    # Assert
    assert (outcomes, package.skills_enabled, package.mcp_enabled) == (
        [0, 0],
        True,
        False,
    )


def test_cli_switch_does_not_rewrite_hand_authored_yaml(isolated_skill_config):
    # Arrange
    from scitex_dev._cli._root import main

    path = isolated_skill_config / "config.yaml"
    path.write_text(_documented_yaml())
    original = path.read_bytes()
    # Act
    result = CliRunner().invoke(
        main, ["dev", "skills", "enable", "scitex-writer", "--yes"]
    )
    # Assert
    assert (result.exit_code, path.read_bytes()) == (0, original)


def test_configuration_skill_python_examples_execute_in_isolated_environment(
    isolated_skill_config,
):
    # Arrange
    (isolated_skill_config / "config.yaml").write_text(_documented_yaml())
    blocks = re.findall(r"```python\n(.*?)```", _GUIDE.read_text(), re.DOTALL)
    if not blocks:
        raise ValueError(
            "The configuration skill contains no Python example to exercise"
        )
    # Act
    observations = []
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
        observations.append(json.loads(result.stdout))
    expected = {
        "path": str(isolated_skill_config / "config.yaml"),
        "skills": False,
        "mcp": True,
    }
    # Assert
    assert observations == [expected] * len(blocks)


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
