"""Tests for scitex_dev._release.entrypoint_imports.

Fixtures are REAL installed distributions, not mocks: each one is an
on-disk directory holding real importable modules plus a real
``*.dist-info/`` carrying real ``METADATA`` and ``entry_points.txt``.
That is byte-for-byte the layout ``pip install`` produces and the layout
a wheel unpacks to, so ``importlib.metadata`` discovers them and the
probe subprocess imports them exactly as it would a published artifact.

Each scenario is a function-scoped fixture that builds its distribution
and runs one real audit; the tests then assert one property each. The
fixtures write files, so they must not be shared across tests (STX-TQ004)
— every test gets its own `tmp_path` and its own probe subprocess.
"""

from __future__ import annotations

import textwrap
import zipfile
from pathlib import Path

import pytest

from scitex_dev._release.entrypoint_imports import (
    EntryPointAuditReport,
    EntryPointProbe,
    audit_entry_point_imports,
    audit_wheel_entry_point_imports,
)

_ABSENT_DEP = "a_dependency_that_is_not_installed_anywhere"


def _install_dist(
    root: Path,
    dist_name: str,
    *,
    version: str = "1.0.0",
    entry_points: str = "",
    modules: dict[str, str] | None = None,
) -> Path:
    """Materialise a real installed distribution under `root`.

    `modules` maps a dotted module path to its source; parent packages
    get an empty `__init__.py`. `entry_points` is the literal
    `entry_points.txt` body (the file is omitted entirely when empty,
    matching a distribution that declares none).
    """
    root.mkdir(parents=True, exist_ok=True)
    for dotted, source in (modules or {}).items():
        parts = dotted.split(".")
        pkg_dir = root
        for part in parts[:-1]:
            pkg_dir = pkg_dir / part
            pkg_dir.mkdir(exist_ok=True)
            init = pkg_dir / "__init__.py"
            if not init.exists():
                init.write_text("")
        (pkg_dir / f"{parts[-1]}.py").write_text(source)

    info = root / f"{dist_name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(exist_ok=True)
    info.joinpath("METADATA").write_text(
        textwrap.dedent(
            f"""\
            Metadata-Version: 2.1
            Name: {dist_name}
            Version: {version}
            """
        )
    )
    info.joinpath("WHEEL").write_text(
        "Wheel-Version: 1.0\n"
        "Generator: test\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )
    if entry_points:
        info.joinpath("entry_points.txt").write_text(entry_points)
    return root


def _zip_as_wheel(site: Path, wheel_path: Path) -> Path:
    """Zip a real installed layout into a real wheel file."""
    with zipfile.ZipFile(wheel_path, "w") as zf:
        for path in sorted(site.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(site).as_posix())
    return wheel_path


# ----------------------------------------------------------------------
# Scenario fixtures — one real distribution + one real audit each
# ----------------------------------------------------------------------


@pytest.fixture
def resolving_report(tmp_path: Path) -> EntryPointAuditReport:
    """Declared target that imports cleanly."""
    site = _install_dist(
        tmp_path / "site",
        "good-dist",
        entry_points="[pytest11]\ngood_plugin = good_pkg.plugin\n",
        modules={"good_pkg.plugin": "VALUE = 1\n"},
    )
    return audit_entry_point_imports("good-dist", search_paths=[site])


@pytest.fixture
def resolving_attr_report(tmp_path: Path) -> EntryPointAuditReport:
    """Declared `module:attr` target whose attribute exists."""
    site = _install_dist(
        tmp_path / "site",
        "attr-dist",
        entry_points="[console_scripts]\nrunme = attr_pkg.cli:main\n",
        modules={"attr_pkg.cli": "def main():\n    return 0\n"},
    )
    return audit_entry_point_imports("attr-dist", search_paths=[site])


@pytest.fixture
def absent_module_report(tmp_path: Path) -> EntryPointAuditReport:
    """Package ships, but the declared SUBMODULE does not exist."""
    site = _install_dist(
        tmp_path / "site",
        "dangling-dist",
        entry_points=(
            "[pytest11]\ndangling_plugin = dangling_pkg._absent_plugin\n"
        ),
        modules={"dangling_pkg.present": "VALUE = 1\n"},
    )
    return audit_entry_point_imports("dangling-dist", search_paths=[site])


@pytest.fixture
def absent_top_level_report(tmp_path: Path) -> EntryPointAuditReport:
    """Nothing named by the target was shipped at all."""
    site = _install_dist(
        tmp_path / "site",
        "vanished-dist",
        entry_points="[pytest11]\nvanished = vanished_pkg.plugin\n",
        modules={"other_pkg.thing": "VALUE = 1\n"},
    )
    return audit_entry_point_imports("vanished-dist", search_paths=[site])


@pytest.fixture
def raising_module_report(tmp_path: Path) -> EntryPointAuditReport:
    """Target module EXISTS; its own import chain raises ImportError."""
    site = _install_dist(
        tmp_path / "site",
        "broken-dist",
        entry_points="[pytest11]\nbroken_plugin = broken_pkg.plugin\n",
        modules={"broken_pkg.plugin": f"import {_ABSENT_DEP}\n"},
    )
    return audit_entry_point_imports("broken-dist", search_paths=[site])


@pytest.fixture
def mixed_failure_report(tmp_path: Path) -> EntryPointAuditReport:
    """One absent target and one raising target in one distribution."""
    site = _install_dist(
        tmp_path / "site",
        "mixed-dist",
        entry_points=(
            "[pytest11]\ngone = mixed_pkg._absent\nraises = mixed_pkg.explodes\n"
        ),
        modules={
            "mixed_pkg.explodes": "raise ImportError('module scope boom')\n"
        },
    )
    return audit_entry_point_imports("mixed-dist", search_paths=[site])


@pytest.fixture
def absent_attr_report(tmp_path: Path) -> EntryPointAuditReport:
    """Module imports, but the declared attribute is not defined."""
    site = _install_dist(
        tmp_path / "site",
        "noattr-dist",
        entry_points="[console_scripts]\nrunme = noattr_pkg.cli:main\n",
        modules={"noattr_pkg.cli": "OTHER = 1\n"},
    )
    return audit_entry_point_imports("noattr-dist", search_paths=[site])


@pytest.fixture
def no_entry_points_site(tmp_path: Path) -> Path:
    """CONTROL: a real distribution declaring no entry points at all."""
    return _install_dist(
        tmp_path / "site",
        "quiet-dist",
        entry_points="",
        modules={"quiet_pkg.thing": "VALUE = 1\n"},
    )


@pytest.fixture
def no_entry_points_report(
    no_entry_points_site: Path,
) -> EntryPointAuditReport:
    """CONTROL ARM: audit of a distribution declaring no entry points."""
    return audit_entry_point_imports(
        "quiet-dist", search_paths=[no_entry_points_site]
    )


@pytest.fixture
def empty_entry_points_report(tmp_path: Path) -> EntryPointAuditReport:
    """CONTROL ARM: entry_points.txt present but declaring nothing."""
    site = _install_dist(
        tmp_path / "site",
        "empty-eps-dist",
        entry_points="\n",
        modules={"empty_eps_pkg.thing": "VALUE = 1\n"},
    )
    return audit_entry_point_imports("empty-eps-dist", search_paths=[site])


@pytest.fixture
def wheel_with_dropped_module_report(
    tmp_path: Path,
) -> EntryPointAuditReport:
    """The packaging bug: correct declaration, module absent from wheel."""
    tmp = tmp_path
    site = _install_dist(
        tmp / "site",
        "wheelbug-dist",
        entry_points="[pytest11]\nplug = wheelbug_pkg.plugin\n",
        modules={"wheelbug_pkg.plugin": "VALUE = 1\n"},
    )
    (site / "wheelbug_pkg" / "plugin.py").unlink()
    wheel = _zip_as_wheel(site, tmp / "wheelbug_dist-1.0.0-py3-none-any.whl")
    return audit_wheel_entry_point_imports(wheel, "wheelbug-dist")


@pytest.fixture
def intact_wheel_report(tmp_path: Path) -> EntryPointAuditReport:
    """A wheel carrying every module its dist-info declares."""
    tmp = tmp_path
    site = _install_dist(
        tmp / "site",
        "wheelok-dist",
        entry_points="[pytest11]\nplug = wheelok_pkg.plugin\n",
        modules={"wheelok_pkg.plugin": "VALUE = 1\n"},
    )
    wheel = _zip_as_wheel(site, tmp / "wheelok_dist-1.0.0-py3-none-any.whl")
    return audit_wheel_entry_point_imports(wheel, "wheelok-dist")


@pytest.fixture
def synthetic_failing_report() -> EntryPointAuditReport:
    """One missing, one broken, one ok — for summary formatting."""
    return EntryPointAuditReport(
        distribution_name="demo",
        probes=[
            EntryPointProbe("pytest11", "a", "m.a", "m.a", status="missing"),
            EntryPointProbe("pytest11", "b", "m.b", "m.b", status="broken"),
            EntryPointProbe("pytest11", "c", "m.c", "m.c", status="ok"),
        ],
    )


# ----------------------------------------------------------------------
# Case 1 — declared target imports cleanly
# ----------------------------------------------------------------------


def test_entry_point_whose_target_imports_is_reported_clean(
    resolving_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = resolving_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is True


def test_entry_point_whose_target_imports_yields_no_failures(
    resolving_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = resolving_report
    # Act
    failures = report.failures
    # Assert
    assert failures == []


def test_entry_point_whose_target_imports_gets_status_ok(
    resolving_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = resolving_report
    # Act
    statuses = [probe.status for probe in report.probes]
    # Assert
    assert statuses == ["ok"]


def test_entry_point_with_attribute_that_resolves_is_reported_clean(
    resolving_attr_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = resolving_attr_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is True


def test_entry_point_value_with_colon_parses_attribute_from_target(
    resolving_attr_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = resolving_attr_report
    # Act
    attr = report.probes[0].attr
    # Assert
    assert attr == "main"


# ----------------------------------------------------------------------
# Case 2 — declared target module does NOT exist -> flagged `missing`
# ----------------------------------------------------------------------


def test_entry_point_with_absent_target_module_is_not_clean(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is False


def test_entry_point_with_absent_target_module_gets_status_missing(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    statuses = [probe.status for probe in report.failures]
    # Assert
    assert statuses == ["missing"]


def test_absent_target_failure_names_the_declared_entry_point(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    name = report.failures[0].name
    # Assert
    assert name == "dangling_plugin"


def test_absent_target_failure_names_the_missing_target_module(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    module = report.failures[0].module
    # Assert
    assert module == "dangling_pkg._absent_plugin"


def test_absent_target_detail_states_the_module_does_not_exist(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    detail = report.failures[0].detail
    # Assert
    assert "DOES NOT EXIST" in detail


def test_absent_target_report_text_carries_entry_point_and_target(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    text = report.report()
    # Assert
    assert "dangling_plugin" in text and "dangling_pkg._absent_plugin" in text


def test_entry_point_whose_top_level_package_is_absent_is_flagged_missing(
    absent_top_level_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_top_level_report
    # Act
    statuses = [probe.status for probe in report.probes]
    # Assert
    assert statuses == ["missing"]


def test_missing_target_in_autoloaded_group_is_marked_autoloaded(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    autoloaded = report.failures[0].is_autoloaded
    # Assert
    assert autoloaded is True


def test_autoloaded_failure_report_warns_it_breaks_tooling_at_startup(
    absent_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_module_report
    # Act
    text = report.report()
    # Assert
    assert "AUTO-LOADED" in text


# ----------------------------------------------------------------------
# Case 3 — target EXISTS but raises on import -> flagged `broken`,
# with a message that does NOT read as "module missing"
# ----------------------------------------------------------------------


def test_entry_point_target_that_raises_on_import_is_not_clean(
    raising_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = raising_module_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is False


def test_entry_point_target_that_raises_on_import_gets_status_broken(
    raising_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = raising_module_report
    # Act
    statuses = [probe.status for probe in report.failures]
    # Assert
    assert statuses == ["broken"]


def test_broken_failure_names_the_target_module_that_exists(
    raising_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = raising_module_report
    # Act
    module = report.failures[0].module
    # Assert
    assert module == "broken_pkg.plugin"


def test_broken_detail_states_the_module_exists_but_failed_to_import(
    raising_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = raising_module_report
    # Act
    detail = report.failures[0].detail
    # Assert
    assert "EXISTS but FAILED to import" in detail


def test_broken_detail_never_claims_the_module_does_not_exist(
    raising_module_report: EntryPointAuditReport,
) -> None:
    # Arrange — the discriminator: an internal ModuleNotFoundError must
    # not be laundered into "the target module does not exist".
    report = raising_module_report
    # Act
    detail = report.failures[0].detail
    # Assert
    assert "DOES NOT EXIST" not in detail


def test_broken_detail_names_the_dependency_that_failed_inside_the_module(
    raising_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = raising_module_report
    # Act
    detail = report.failures[0].detail
    # Assert
    assert _ABSENT_DEP in detail


def test_absent_target_and_raising_target_are_partitioned_missing_vs_broken(
    mixed_failure_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = mixed_failure_report
    # Act
    buckets = (
        [probe.name for probe in report.missing],
        [probe.name for probe in report.broken],
    )
    # Assert
    assert buckets == (["gone"], ["raises"])


def test_mixed_distribution_reports_both_entry_points_as_failures(
    mixed_failure_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = mixed_failure_report
    # Act
    count = len(report.failures)
    # Assert
    assert count == 2


def test_entry_point_attribute_absent_from_importable_module_is_flagged_broken(
    absent_attr_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_attr_report
    # Act
    statuses = [probe.status for probe in report.failures]
    # Assert
    assert statuses == ["broken"]


def test_absent_attribute_detail_names_the_undefined_attribute(
    absent_attr_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = absent_attr_report
    # Act
    detail = report.failures[0].detail
    # Assert
    assert "attribute 'main' is not defined" in detail


# ----------------------------------------------------------------------
# CONTROL ARM — a distribution declaring NO entry points is CLEAN.
# Without this, "flag everything" would pass as a fix.
# ----------------------------------------------------------------------


def test_control_fixture_really_ships_no_entry_points_file(
    no_entry_points_site: Path,
) -> None:
    # Arrange
    site = no_entry_points_site
    # Act
    found = list(site.rglob("entry_points.txt"))
    # Assert
    assert found == []


def test_distribution_declaring_no_entry_points_yields_no_probes(
    no_entry_points_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = no_entry_points_report
    # Act
    probes = report.probes
    # Assert
    assert probes == []


def test_distribution_declaring_no_entry_points_is_clean_not_flagged(
    no_entry_points_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = no_entry_points_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is True


def test_distribution_declaring_no_entry_points_reports_zero_failures(
    no_entry_points_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = no_entry_points_report
    # Act
    failures = report.failures
    # Assert
    assert failures == []


def test_distribution_with_empty_entry_points_file_is_clean_not_flagged(
    empty_entry_points_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = empty_entry_points_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is True


def test_distribution_with_empty_entry_points_file_yields_no_probes(
    empty_entry_points_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = empty_entry_points_report
    # Act
    probes = report.probes
    # Assert
    assert probes == []


# ----------------------------------------------------------------------
# Artifact-level entry: the gate reads the BUILT WHEEL, not the source
# ----------------------------------------------------------------------


def test_wheel_declaring_a_module_it_does_not_carry_is_not_clean(
    wheel_with_dropped_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = wheel_with_dropped_module_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is False


def test_wheel_declaring_a_module_it_does_not_carry_names_that_module(
    wheel_with_dropped_module_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = wheel_with_dropped_module_report
    # Act
    module = report.missing[0].module
    # Assert
    assert module == "wheelbug_pkg.plugin"


def test_wheel_carrying_every_declared_module_is_clean(
    intact_wheel_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = intact_wheel_report
    # Act
    clean = report.is_clean
    # Assert
    assert clean is True


def test_wheel_audit_probes_every_entry_point_the_dist_info_declares(
    intact_wheel_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = intact_wheel_report
    # Act
    count = len(report.probes)
    # Assert
    assert count == 1


# ----------------------------------------------------------------------
# Report surface
# ----------------------------------------------------------------------


def test_summary_counts_failing_entry_points_against_the_total(
    synthetic_failing_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = synthetic_failing_report
    # Act
    summary = report.summary()
    # Assert
    assert "2/3" in summary


def test_summary_counts_missing_targets_separately_from_broken_imports(
    synthetic_failing_report: EntryPointAuditReport,
) -> None:
    # Arrange
    report = synthetic_failing_report
    # Act
    summary = report.summary()
    # Assert
    assert "1 missing target" in summary and "1 broken import" in summary


# EOF
