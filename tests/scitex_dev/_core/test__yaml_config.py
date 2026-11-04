"""Strict exposure reads refuse malformed selections without changing legacy reads."""

import os
import subprocess
import sys

import pytest

from scitex_dev._core.config import load_config
from scitex_dev.exposure import load_exposure_policy


@pytest.mark.parametrize(
    "content",
    [
        "packages: not-a-list",
        "packages: {owned: false}",
        "packages: null",
        "packages: false",
        "packages: 42",
        "packages: [owned]",
        "packages: [null]",
        "packages: [[]]",
        "packages: [{}]",
        "packages: [{pypi_name: owned}]",
        "packages: [{name: null}]",
        "packages: [{name: 42}]",
        "packages: [{name: []}]",
        'packages: [{name: ""}]',
        'packages: [{name: " "}]',
        "packages: [{name: ../owned}]",
    ],
)
def test_strict_packages_structure_refuses(tmp_path, content):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text(content)
    state = tmp_path / "absent-state.json"
    # Act
    # Assert
    with pytest.raises((TypeError, ValueError)):
        load_exposure_policy(config, knob_state_path=state)


@pytest.mark.parametrize("content", ["", "{}", "packages: []"])
def test_empty_selections_keep_defaults_without_creating_state(tmp_path, content):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text(content)
    state = tmp_path / "absent-state.json"
    # Act
    policy = load_exposure_policy(config, knob_state_path=state)
    # Assert
    assert (
        tuple(
            policy.is_enabled("unconfigured-owner", kind)
            for kind in ("cli", "mcp", "skills")
        ),
        config.read_text(),
        state.exists(),
    ) == ((True, True, True), content, False)


@pytest.mark.parametrize(
    "content",
    ["packages: not-a-list", "packages: {}", "packages: null", "packages: [owned]"],
)
def test_legacy_resolver_keeps_existing_ignored_structure(tmp_path, content):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text(content)
    defaults = load_config(tmp_path / "missing.yaml")
    # Act
    legacy = load_config(config)
    # Assert
    assert legacy.packages == defaults.packages


def test_invalid_selection_refuses_before_provider_import_or_write(tmp_path):
    # Arrange
    config = tmp_path / "config.yaml"
    config.write_text("packages: not-a-list")
    site = tmp_path / "installed"
    site.mkdir()
    info = site / "poison_provider-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: poison-provider\nVersion: 1.0\n"
    )
    (info / "entry_points.txt").write_text(
        "[scitex.cli]\npoison = poison_provider:main\n"
    )
    (site / "poison_provider.py").write_text(
        "raise RuntimeError('provider imported')\n"
    )
    code = """
import logging
import os
import sys
# The caller owns logging; dependency imports must preserve this handler.
logging.getLogger().addHandler(logging.NullHandler())
from scitex_dev.exposure import load_exposure_policy
def refuse_mutations(event, args):
    if event == 'open' and ((isinstance(args[1], str) and any(c in args[1] for c in 'wax+'))
                            or args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)):
        raise RuntimeError('unexpected write')
    if event in {'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir', 'os.chmod',
                 'os.truncate', 'os.chown', 'os.utime', 'os.link', 'os.symlink', 'subprocess.Popen'}:
        raise RuntimeError('unexpected mutation')
sys.addaudithook(refuse_mutations)
try:
    load_exposure_policy(sys.argv[1], knob_state_path=sys.argv[2])
except (TypeError, ValueError):
    assert 'poison_provider' not in sys.modules
    print('refused-without-provider-import-or-write')
else:
    raise RuntimeError('malformed selection silently accepted')
"""
    environment = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    environment["PYTHONPATH"] = os.pathsep.join([str(site), *sys.path])
    # Act
    result = subprocess.run(
        [sys.executable, "-B", "-c", code, str(config), str(tmp_path / "absent.json")],
        env=environment,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    # Assert
    assert (result.returncode, result.stdout.strip(), result.stderr) == (
        0,
        "refused-without-provider-import-or-write",
        "",
    )
