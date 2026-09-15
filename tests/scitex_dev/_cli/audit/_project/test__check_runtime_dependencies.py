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


def test_ps233_is_registered_as_an_error() -> None:
    assert RULES["PS-233"].severity == "E"


def test_function_local_psutil_default_path_missing_fires(tmp_path) -> None:
    """Reference incident: tests inject process_iter, production imports psutil."""
    _make_package(
        tmp_path,
        "def _default_process_iter():\n"
        "    import psutil\n"
        "    return psutil.process_iter(['pid', 'cmdline'])\n\n"
        "def reconcile_inbox_sidecars(process_iter=None):\n"
        "    iterator = process_iter or _default_process_iter\n"
        "    return list(iterator())\n",
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_reconcile.py").write_text(
        "def test_with_injected_process_iter():\n"
        "    process_iter = lambda: []\n"
        "    assert list(process_iter()) == []\n",
        encoding="utf-8",
    )

    out = _audit(tmp_path)

    assert len(out) == 1
    assert out[0].rule == "PS-233"
    assert "psutil" in out[0].detail
    assert "[project.dependencies]" in out[0].detail
    assert "_inbox_sidecar_reconcile.py:2" in out[0].where


def test_declaring_psutil_in_core_satisfies_function_local_import(tmp_path) -> None:
    _make_package(
        tmp_path,
        "def _default_process_iter():\n"
        "    import psutil\n"
        "    return psutil.process_iter()\n",
        core=("psutil>=5.9",),
    )

    assert _audit(tmp_path) == []


def test_unguarded_extra_import_requires_core(tmp_path) -> None:
    _make_package(
        tmp_path,
        "def collect():\n    import psutil\n    return psutil.cpu_count()\n",
        extras={"all": ("psutil>=5.9",)},
    )

    out = _audit(tmp_path)

    assert len(out) == 1
    assert "declared only in optional extra `[all]`" in out[0].detail
    assert "Move it to `[project.dependencies]`" in out[0].detail


def test_guarded_import_may_live_in_runtime_extra(tmp_path) -> None:
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

    assert _audit(tmp_path) == []


def test_broad_exception_guard_may_live_in_runtime_extra(tmp_path) -> None:
    _make_package(
        tmp_path,
        "try:\n    import psutil\nexcept Exception:\n    psutil = None\n",
        extras={"all": ("psutil>=5.9",)},
    )

    assert _audit(tmp_path) == []


def test_try_around_function_definition_does_not_guard_deferred_import(
    tmp_path,
) -> None:
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

    out = _audit(tmp_path)

    assert len(out) == 1
    assert "import is unguarded" in out[0].detail


def test_guarded_but_undeclared_import_requires_runtime_extra(tmp_path) -> None:
    _make_package(
        tmp_path,
        "try:\n    import psutil\nexcept ModuleNotFoundError:\n    psutil = None\n",
    )

    out = _audit(tmp_path)

    assert len(out) == 1
    assert "consumer runtime extra" in out[0].detail


def test_dev_extra_does_not_satisfy_guarded_runtime_import(tmp_path) -> None:
    _make_package(
        tmp_path,
        "try:\n    import psutil\nexcept ImportError:\n    psutil = None\n",
        extras={"dev": ("psutil",)},
    )

    assert len(_audit(tmp_path)) == 1


def test_type_checking_only_import_is_ignored(tmp_path) -> None:
    _make_package(
        tmp_path,
        "from typing import TYPE_CHECKING as TC\n"
        "if TC:\n"
        "    import psutil\n",
    )

    assert _audit(tmp_path) == []


def test_typing_module_alias_type_checking_import_is_ignored(tmp_path) -> None:
    _make_package(
        tmp_path,
        "import typing as t\nif t.TYPE_CHECKING:\n    import psutil\n",
    )

    assert _audit(tmp_path) == []


def test_stdlib_relative_and_own_package_imports_are_ignored(tmp_path) -> None:
    _make_package(
        tmp_path,
        "import json\n"
        "import scitex_agent_container\n"
        "from . import sibling\n",
    )

    assert _audit(tmp_path) == []


def test_own_namespace_package_import_is_ignored(tmp_path) -> None:
    _make_package(tmp_path, "import scitex_extension\n")
    namespace = tmp_path / "src" / "scitex_extension"
    namespace.mkdir()
    (namespace / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")

    assert _audit(tmp_path) == []


def test_known_distribution_alias_is_compared_to_metadata(tmp_path) -> None:
    _make_package(tmp_path, "import yaml\n")

    out = _audit(tmp_path)

    assert len(out) == 1
    assert "`pyyaml` is undeclared" in out[0].detail


def test_known_distribution_alias_passes_when_declared(tmp_path) -> None:
    _make_package(tmp_path, "import yaml\n", core=("PyYAML>=6",))

    assert _audit(tmp_path) == []


def test_unknown_import_root_is_excluded_instead_of_guessed(tmp_path) -> None:
    _make_package(tmp_path, "import organisation_private_runtime\n")

    assert _audit(tmp_path) == []


def test_false_branch_import_is_not_runtime(tmp_path) -> None:
    _make_package(tmp_path, "if False:\n    import psutil\n")

    assert _audit(tmp_path) == []
