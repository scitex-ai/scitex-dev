"""PS-233 runtime dependency declaration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scitex_dev._cli.audit._project._check_runtime_dependencies import (
    check_ps233_runtime_dependencies,
)
from scitex_dev._cli.audit._project._registry import RULES


@dataclass
class _StubViolation:
    rule: str
    where: str
    detail: str


def _make_package(
    repo: Path,
    source: str,
    *,
    core: tuple[str, ...] = (),
    extras: dict[str, tuple[str, ...]] | None = None,
) -> None:
    dependencies = ", ".join(repr(dep) for dep in core)
    extra_lines = []
    for name, requirements in (extras or {}).items():
        rendered = ", ".join(repr(dep) for dep in requirements)
        extra_lines.append(f"{name} = [{rendered}]")
    extras_block = ""
    if extra_lines:
        extras_block = "[project.optional-dependencies]\n" + "\n".join(extra_lines)
    (repo / "pyproject.toml").write_text(
        "[project]\n"
        'name = "scitex-agent-container"\n'
        f"dependencies = [{dependencies}]\n"
        f"{extras_block}\n",
        encoding="utf-8",
    )
    package = repo / "src" / "scitex_agent_container"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "_inbox_sidecar_reconcile.py").write_text(source, encoding="utf-8")


def _audit(repo: Path) -> list[_StubViolation]:
    out: list[_StubViolation] = []
    check_ps233_runtime_dependencies(
        repo, "scitex-agent-container", _StubViolation, out
    )
    return out


# Reference incident: the test suite injects `process_iter`, so nothing in the
# suite ever reaches `_default_process_iter` — which is the only caller of the
# lazily imported psutil. The import is unguarded, so a fresh install of the
# distribution is incomplete and the audit must say so.
_REFERENCE_INCIDENT_SOURCE = (
    "def _default_process_iter():\n"
    "    import psutil\n"
    "    return psutil.process_iter(['pid', 'cmdline'])\n\n"
    "def reconcile_inbox_sidecars(process_iter=None):\n"
    "    iterator = process_iter or _default_process_iter\n"
    "    return list(iterator())\n"
)

_REFERENCE_INCIDENT_TEST = (
    "def test_with_injected_process_iter():\n"
    "    process_iter = lambda: []\n"
    "    assert list(process_iter()) == []\n"
)


def _make_reference_incident_repo(repo: Path) -> None:
    """Build the injected-process_iter incident fixture under *repo*."""
    _make_package(repo, _REFERENCE_INCIDENT_SOURCE)
    tests = repo / "tests"
    tests.mkdir()
    (tests / "test_reconcile.py").write_text(
        _REFERENCE_INCIDENT_TEST, encoding="utf-8"
    )


def test_ps233_is_registered_as_an_error() -> None:
    # Arrange
    rule = RULES["PS-233"]
    # Act
    severity = rule.severity
    # Assert
    assert severity == "E"


def test_reference_incident_reports_exactly_one_violation(tmp_path) -> None:
    # Arrange
    _make_reference_incident_repo(tmp_path)
    # Act
    out = _audit(tmp_path)
    # Assert
    assert len(out) == 1


def test_reference_incident_violation_carries_ps233_code(tmp_path) -> None:
    # Arrange
    _make_reference_incident_repo(tmp_path)
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out[0].rule == "PS-233"


def test_reference_incident_detail_names_psutil_distribution(tmp_path) -> None:
    # Arrange
    _make_reference_incident_repo(tmp_path)
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "psutil" in out[0].detail


def test_reference_incident_remedy_points_at_core_dependencies(tmp_path) -> None:
    # Arrange
    _make_reference_incident_repo(tmp_path)
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "[project.dependencies]" in out[0].detail


def test_reference_incident_locates_the_import_line(tmp_path) -> None:
    # Arrange
    _make_reference_incident_repo(tmp_path)
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "_inbox_sidecar_reconcile.py:2" in out[0].where


def test_declaring_psutil_in_core_satisfies_function_local_import(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "def _default_process_iter():\n"
        "    import psutil\n"
        "    return psutil.process_iter()\n",
        core=("psutil>=5.9",),
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_unguarded_extra_import_reports_single_violation(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "def collect():\n    import psutil\n    return psutil.cpu_count()\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert len(out) == 1


def test_unguarded_extra_import_detail_names_the_extra(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "def collect():\n    import psutil\n    return psutil.cpu_count()\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "declared only in optional extra `[all]`" in out[0].detail


def test_unguarded_extra_import_remedy_moves_it_to_core(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "def collect():\n    import psutil\n    return psutil.cpu_count()\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "Move it to `[project.dependencies]`" in out[0].detail


def test_guarded_import_may_live_in_runtime_extra(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "def metrics():\n"
        "    try:\n"
        "        import psutil\n"
        "    except ImportError:\n"
        "        return {}\n"
        "    return {'cpu': psutil.cpu_count()}\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_broad_exception_guard_may_live_in_runtime_extra(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "try:\n    import psutil\nexcept Exception:\n    psutil = None\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_try_around_function_definition_reports_single_violation(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "try:\n"
        "    def metrics():\n"
        "        import psutil\n"
        "        return psutil.cpu_count()\n"
        "except ImportError:\n"
        "    pass\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert len(out) == 1


def test_try_around_function_definition_detail_says_unguarded(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "try:\n"
        "    def metrics():\n"
        "        import psutil\n"
        "        return psutil.cpu_count()\n"
        "except ImportError:\n"
        "    pass\n",
        extras={"all": ("psutil>=5.9",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "import is unguarded" in out[0].detail


def test_guarded_undeclared_import_is_the_plugin_form(tmp_path) -> None:
    # The guard IS the contract: a capability wrapped in try/except ImportError
    # is optional, so it needs no declaration. Requiring one forced the
    # declaration that closed a dependency cycle with a package that requires
    # this project -- which is why this expectation is the inverse of the
    # original rule.
    # Arrange
    _make_package(
        tmp_path,
        "try:\n    import psutil\nexcept ModuleNotFoundError:\n    psutil = None\n",
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_guarded_import_declared_in_dev_extra_is_allowed(tmp_path) -> None:
    # Declaring an optional capability in an extra stays legal; only an
    # unguarded import may not hide there.
    # Arrange
    _make_package(
        tmp_path,
        "try:\n    import psutil\nexcept ImportError:\n    psutil = None\n",
        extras={"dev": ("psutil",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_unguarded_import_declared_only_in_dev_extra_still_reports(tmp_path) -> None:
    # The relaxation must not let a hard requirement hide in [dev].
    # Arrange
    _make_package(
        tmp_path,
        "def collect():\n    import psutil\n    return psutil.cpu_count()\n",
        extras={"dev": ("psutil",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert len(out) == 1


def test_unguarded_import_declared_only_in_dev_extra_names_core_target(
    tmp_path,
) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "def collect():\n    import psutil\n    return psutil.cpu_count()\n",
        extras={"dev": ("psutil",)},
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "Move it to `[project.dependencies]`" in out[0].detail


def test_type_checking_only_import_is_ignored(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "from typing import TYPE_CHECKING as TC\n"
        "if TC:\n"
        "    import psutil\n",
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_typing_module_alias_type_checking_import_is_ignored(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "import typing as t\nif t.TYPE_CHECKING:\n    import psutil\n",
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_stdlib_relative_and_own_package_imports_are_ignored(tmp_path) -> None:
    # Arrange
    _make_package(
        tmp_path,
        "import json\n"
        "import scitex_agent_container\n"
        "from . import sibling\n",
    )
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_own_namespace_package_import_is_ignored(tmp_path) -> None:
    # Arrange
    _make_package(tmp_path, "import scitex_extension\n")
    namespace = tmp_path / "src" / "scitex_extension"
    namespace.mkdir()
    (namespace / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_known_distribution_alias_reports_single_violation(tmp_path) -> None:
    # Arrange
    _make_package(tmp_path, "import yaml\n")
    # Act
    out = _audit(tmp_path)
    # Assert
    assert len(out) == 1


def test_known_distribution_alias_detail_names_pyyaml(tmp_path) -> None:
    # Arrange
    _make_package(tmp_path, "import yaml\n")
    # Act
    out = _audit(tmp_path)
    # Assert
    assert "`pyyaml` is undeclared" in out[0].detail


def test_known_distribution_alias_passes_when_declared(tmp_path) -> None:
    # Arrange
    _make_package(tmp_path, "import yaml\n", core=("PyYAML>=6",))
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_unknown_import_root_is_excluded_instead_of_guessed(tmp_path) -> None:
    # Arrange
    _make_package(tmp_path, "import organisation_private_runtime\n")
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []


def test_false_branch_import_is_not_runtime(tmp_path) -> None:
    # Arrange
    _make_package(tmp_path, "if False:\n    import psutil\n")
    # Act
    out = _audit(tmp_path)
    # Assert
    assert out == []
