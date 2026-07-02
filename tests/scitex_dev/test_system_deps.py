"""Tests for scitex_dev.system_deps (federated apt-dependency aggregation).

Uses the real ``extra_providers`` injection seam (no mocks) to supply fake
providers, mirroring how discover_jobs is tested.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from scitex_dev._cli import main
from scitex_dev._cli.ecosystem._cmds._system_deps import (
    _do_install,
    _read_baseline,
    _superset_delta,
)
from scitex_dev.system_deps import SystemDepSpec, discover_system_deps


def test_discover_returns_specs_from_an_injected_provider():
    # Arrange
    def provide():
        return [SystemDepSpec("ffmpeg", "audio decode", "scitex-audio")]

    # Act
    packages = [d.package for d in discover_system_deps(include_entry_points=False, extra_providers=[provide])]
    # Assert
    assert packages == ["ffmpeg"]


def test_discover_dedups_by_package_first_provider_wins():
    # Arrange
    def first():
        return [SystemDepSpec("ffmpeg", "from-first", "scitex-audio")]

    def second():
        return [SystemDepSpec("ffmpeg", "from-second", "scitex-cv")]

    # Act
    deps = discover_system_deps(include_entry_points=False, extra_providers=[first, second])
    # Assert
    assert [(d.package, d.provider) for d in deps] == [("ffmpeg", "scitex-audio")]


def test_discover_sorts_by_package_name():
    # Arrange
    def provide():
        return [
            SystemDepSpec("portaudio19-dev", "mic capture", "scitex-audio"),
            SystemDepSpec("ffmpeg", "audio decode", "scitex-audio"),
        ]

    # Act
    packages = [d.package for d in discover_system_deps(include_entry_points=False, extra_providers=[provide])]
    # Assert
    assert packages == ["ffmpeg", "portaudio19-dev"]


def test_discover_skips_a_provider_that_raises():
    # Arrange
    def boom():
        raise RuntimeError("broken leaf provider")

    def ok():
        return [SystemDepSpec("biber", "bibliography", "scitex-writer")]

    # Act
    packages = [d.package for d in discover_system_deps(include_entry_points=False, extra_providers=[boom, ok])]
    # Assert
    assert packages == ["biber"]


def test_spec_rejects_empty_package():
    # Arrange
    empty_package = ""

    # Act
    def construct():
        return SystemDepSpec(empty_package, "purpose", "scitex-writer")

    # Assert
    with pytest.raises(ValueError):
        construct()


def test_spec_carries_optional_apt_repo():
    # Arrange
    spec = SystemDepSpec("apptainer", "containers", "sac", apt_repo="ppa:apptainer/ppa")
    # Act
    apt_repo = spec.apt_repo
    # Assert
    assert apt_repo == "ppa:apptainer/ppa"


def test_cli_system_deps_list_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "system-deps", "list"])
    # Assert
    assert result.exit_code == 0


def test_cli_system_deps_list_json_emits_an_array():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "system-deps", "list", "--json"])
    # Assert
    assert result.output.strip().startswith("[")


def test_cli_system_deps_default_table_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "system-deps"])
    # Assert
    assert result.exit_code == 0


def test_cli_system_deps_install_defaults_to_dry_run_exits_zero():
    # Arrange
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["ecosystem", "system-deps", "install"])
    # Assert
    assert result.exit_code == 0


def test_do_install_dry_run_previews_without_running():
    # Arrange
    deps = [SystemDepSpec("ffmpeg", "decode", "scitex-audio", apt_repo="ppa:x/y")]
    # Act
    rc = _do_install(deps, dry_run=True)
    # Assert
    assert rc == 0


def test_superset_delta_flags_a_missing_baseline_package():
    # Arrange
    aggregated = {"ffmpeg"}
    baseline = {"ffmpeg", "biber"}
    # Act
    missing, _added = _superset_delta(aggregated, baseline)
    # Assert
    assert missing == ["biber"]


def test_superset_delta_reports_packages_added_by_providers():
    # Arrange
    aggregated = {"ffmpeg", "biber"}
    baseline = {"ffmpeg"}
    # Act
    _missing, added = _superset_delta(aggregated, baseline)
    # Assert
    assert added == ["biber"]


def test_read_baseline_skips_comments_and_blank_lines(tmp_path):
    # Arrange
    baseline_file = tmp_path / "recipe-apt.txt"
    baseline_file.write_text("ffmpeg\n\n# a comment\nbiber  # inline\n")
    # Act
    names = _read_baseline(str(baseline_file))
    # Assert
    assert names == {"ffmpeg", "biber"}


def test_cli_check_superset_is_green_on_an_empty_baseline(tmp_path):
    # Arrange
    baseline_file = tmp_path / "empty.txt"
    baseline_file.write_text("# nothing required\n")
    # Act
    result = CliRunner().invoke(
        main,
        ["ecosystem", "system-deps", "check-superset", "--baseline", str(baseline_file)],
    )
    # Assert
    assert result.exit_code == 0


def test_cli_check_superset_is_red_on_an_undeclared_package(tmp_path):
    # Arrange
    baseline_file = tmp_path / "recipe.txt"
    baseline_file.write_text("zzz-not-a-declared-apt-pkg\n")
    # Act
    result = CliRunner().invoke(
        main,
        ["ecosystem", "system-deps", "check-superset", "--baseline", str(baseline_file)],
    )
    # Assert
    assert result.exit_code == 1


def test_cli_check_superset_json_reports_a_red_verdict(tmp_path):
    # Arrange
    baseline_file = tmp_path / "recipe.txt"
    baseline_file.write_text("zzz-not-a-declared-apt-pkg\n")
    # Act
    result = CliRunner().invoke(
        main,
        [
            "ecosystem",
            "system-deps",
            "check-superset",
            "--baseline",
            str(baseline_file),
            "--json",
        ],
    )
    # Assert
    assert json.loads(result.output)["verdict"] == "red"
