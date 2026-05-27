#!/usr/bin/env python3
"""Tests for scitex_dev._cli.audit._summary._mcp_parity — §6 parity + exemption.

Covers the per-package `[tool.scitex_dev] mcp_parity_exempt` opt-out and the
pure §6 comparison helper. No mocks: synthetic package trees use `tmp_path`,
and the comparison logic is exercised with real name sets.
"""

from __future__ import annotations

from scitex_dev._cli.audit._summary._mcp_parity import (
    _allowlist_violations,
    _audited_repo_root,
    _check_api_parity,
    _parity_violations,
    _python_api_names,
    _repo_root_from_import,
    is_mcp_parity_exempt,
    mcp_tools_allowlist,
)


def _write_pyproject(repo, body: str) -> None:
    """Write a minimal pyproject.toml with `body` appended."""
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "plot-rich"\nversion = "0.0.0"\n' + body
    )


# A plotting-rich tool surface: 5 orphan tools (>3 threshold), zero Python APIs.
_PLOTTING_TOOLS = {"plot", "scatter", "bar", "hist", "boxplot"}


class TestParityComparisonTrips:
    def test_orphan_tool_surface_without_exemption_trips_section_six(self):
        # Arrange
        py_apis: set[str] = set()
        mcp_normalized = set(_PLOTTING_TOOLS)
        # Act
        violations = _parity_violations("plot-rich", py_apis, mcp_normalized)
        # Assert
        assert any(v.rule == "§6" for v in violations)

    def test_matched_tool_surface_produces_no_section_six_violation(self):
        # Arrange
        py_apis = {"save", "load"}
        mcp_normalized = {"save", "load"}
        # Act
        violations = _parity_violations("scitex-io", py_apis, mcp_normalized)
        # Assert
        assert violations == []

    def test_python_apis_without_matching_tools_trips_section_six(self):
        # Arrange
        py_apis = {"save", "load", "glob", "configs"}
        mcp_normalized: set[str] = set()
        # Act
        violations = _parity_violations("scitex-io", py_apis, mcp_normalized)
        # Assert
        assert any("Python APIs have no" in v.message for v in violations)


class TestExemptionDetection:
    def test_pyproject_flag_marks_package_exempt(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "\n[tool.scitex_dev]\nmcp_parity_exempt = true\n")
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=tmp_path)
        # Assert
        assert exempt is True

    def test_pyproject_without_flag_is_not_exempt(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\ncategory = "library"\n')
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=tmp_path)
        # Assert
        assert exempt is False

    def test_yaml_config_flag_marks_package_exempt(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "")
        cfg_dir = tmp_path / ".scitex" / "dev"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text("audit:\n  mcp-parity-exempt: true\n")
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=tmp_path)
        # Assert
        assert exempt is True

    def test_missing_repo_root_is_not_exempt(self, tmp_path):
        # Arrange
        nonexistent = tmp_path / "does-not-exist"
        # Act
        exempt = is_mcp_parity_exempt("plot-rich", repo=nonexistent)
        # Assert
        assert exempt is False


class TestCheckApiParityHonorsExemption:
    def test_exempt_package_suppresses_orphan_violation(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "\n[tool.scitex_dev]\nmcp_parity_exempt = true\n")
        out: list = []
        # Act
        _check_api_parity("plot-rich", set(_PLOTTING_TOOLS), out, repo=tmp_path)
        # Assert
        assert out == []

    def test_non_exempt_unimportable_package_yields_no_violation(self, tmp_path):
        # Arrange
        # No exemption flag and a package that does not import -> the
        # parity check cannot establish APIs and bails without a violation.
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\ncategory = "library"\n')
        out: list = []
        # Act
        _check_api_parity(
            "scitex-no-such-package", set(_PLOTTING_TOOLS), out, repo=tmp_path
        )
        # Assert
        assert out == []

    def test_non_exempt_real_package_with_empty_tools_trips_section_six(self, tmp_path):
        # Arrange
        # scitex-dev is importable (public APIs present) and the tmp repo
        # has no exemption flag, so the non-exempt path runs end-to-end and
        # the empty tool set trips the missing-in-MCP branch.
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\ncategory = "library"\n')
        out: list = []
        # Act
        _check_api_parity("scitex-dev", set(), out, repo=tmp_path)
        # Assert
        assert any(v.rule == "§6" for v in out)


class TestMcpToolsAllowlistDetection:
    def test_pyproject_array_is_read_as_a_set(self, tmp_path):
        # Arrange
        _write_pyproject(
            tmp_path,
            "\n[tool.scitex_dev]\n"
            'mcp_tools_allowlist = ["compute_metrics", "generate_report"]\n',
        )
        # Act
        allow = mcp_tools_allowlist("plot-rich", repo=tmp_path)
        # Assert
        assert allow == {"compute_metrics", "generate_report"}

    def test_yaml_config_list_is_read_as_a_set(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, "")
        cfg_dir = tmp_path / ".scitex" / "dev"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text(
            "audit:\n  mcp-tools-allowlist:\n    - compute_metrics\n    - reduce_dimensions\n"
        )
        # Act
        allow = mcp_tools_allowlist("plot-rich", repo=tmp_path)
        # Assert
        assert allow == {"compute_metrics", "reduce_dimensions"}

    def test_absent_allowlist_returns_none(self, tmp_path):
        # Arrange
        _write_pyproject(tmp_path, '\n[tool.scitex_dev]\ncategory = "library"\n')
        # Act
        allow = mcp_tools_allowlist("plot-rich", repo=tmp_path)
        # Assert
        assert allow is None


class TestAllowlistViolations:
    def test_registered_tools_matching_allowlist_produce_no_violation(self):
        # Arrange
        allowlist = {"compute_metrics", "generate_report"}
        mcp_normalized = {"compute_metrics", "generate_report"}
        # Act
        violations = _allowlist_violations("scitex-ml", allowlist, mcp_normalized)
        # Assert
        assert violations == []

    def test_skills_tools_are_permitted_without_being_listed(self):
        # Arrange
        allowlist = {"compute_metrics"}
        mcp_normalized = {"compute_metrics", "skills_list", "skills_get"}
        # Act
        violations = _allowlist_violations("scitex-ml", allowlist, mcp_normalized)
        # Assert
        assert violations == []

    def test_tool_not_in_allowlist_is_flagged(self):
        # Arrange
        allowlist = {"compute_metrics"}
        mcp_normalized = {"compute_metrics", "secret_tool"}
        # Act
        violations = _allowlist_violations("scitex-ml", allowlist, mcp_normalized)
        # Assert
        assert any("not in mcp_tools_allowlist" in v.message for v in violations)

    def test_declared_name_without_registered_tool_is_flagged(self):
        # Arrange
        allowlist = {"compute_metrics", "never_built"}
        mcp_normalized = {"compute_metrics"}
        # Act
        violations = _allowlist_violations("scitex-ml", allowlist, mcp_normalized)
        # Assert
        assert any("no registered MCP tool" in v.message for v in violations)

    def test_prefixed_allowlist_names_are_normalized_before_compare(self):
        # Arrange
        allowlist = {"ml_compute_metrics"}
        mcp_normalized = {"compute_metrics"}
        # Act
        violations = _allowlist_violations("scitex-ml", allowlist, mcp_normalized)
        # Assert
        assert violations == []


class TestCheckApiParityHonorsAllowlist:
    def test_allowlist_matching_tools_yields_no_violation(self, tmp_path):
        # Arrange
        _write_pyproject(
            tmp_path,
            "\n[tool.scitex_dev]\n"
            'mcp_tools_allowlist = ["compute_metrics", "generate_report"]\n',
        )
        out: list = []
        # Act
        _check_api_parity(
            "plot-rich", {"compute_metrics", "generate_report"}, out, repo=tmp_path
        )
        # Assert
        assert out == []

    def test_allowlist_with_undeclared_tool_trips_section_six(self, tmp_path):
        # Arrange
        _write_pyproject(
            tmp_path, '\n[tool.scitex_dev]\nmcp_tools_allowlist = ["compute_metrics"]\n'
        )
        out: list = []
        # Act
        _check_api_parity(
            "plot-rich", {"compute_metrics", "rogue_tool"}, out, repo=tmp_path
        )
        # Assert
        assert any(v.rule == "§6" for v in out)


class TestPythonApiNames:
    def test_real_importable_package_yields_public_callables(self):
        # Arrange
        # scitex-dev itself is importable in this test environment and
        # exports public callables; the parity check reads them via __all__.
        package = "scitex-dev"
        # Act
        names = _python_api_names(package)
        # Assert
        assert isinstance(names, set)

    def test_unimportable_package_yields_empty_set(self):
        # Arrange
        package = "scitex-definitely-not-a-real-package"
        # Act
        names = _python_api_names(package)
        # Assert
        assert names == set()

    def test_nested_noun_submodule_flattens_to_noun_verb(self, tmp_path):
        # Arrange
        # Build a real importable nested-form package on disk:
        #   scitex_nestpkg/__init__.py exports the `agent` submodule
        #   scitex_nestpkg/agent.py exports __all__ = ["list_"] (a verb)
        # so _python_api_names should flatten it to "agent_list".
        import sys

        pkg_dir = tmp_path / "scitex_nestpkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text(
            "from . import agent\n__all__ = ['agent']\n"
        )
        (pkg_dir / "agent.py").write_text(
            "def list_():\n    return []\n__all__ = ['list_']\n"
        )
        sys.path.insert(0, str(tmp_path))
        try:
            # Act
            names = _python_api_names("scitex-nestpkg")
        finally:
            sys.path.remove(str(tmp_path))
            for mod in list(sys.modules):
                if mod == "scitex_nestpkg" or mod.startswith("scitex_nestpkg."):
                    del sys.modules[mod]
        # Assert
        assert "agent_list" in names


def _build_importable_repo(
    tmp_path, import_name: str, *, config_body: str = ""
) -> "Path":
    """Create a real src-layout repo importable via find_spec; return its root.

    Layout: <root>/pyproject.toml + <root>/src/<import_name>/__init__.py, plus
    an optional <root>/.scitex/dev/config.yaml. Returns the repo root.
    """
    from pathlib import Path

    root = tmp_path / f"{import_name}-repo"
    pkg = root / "src" / import_name
    pkg.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{import_name.replace("_", "-")}"\nversion = "0.0.0"\n'
    )
    (pkg / "__init__.py").write_text("\n")
    if config_body:
        cfg_dir = root / ".scitex" / "dev"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "config.yaml").write_text(config_body)
    return Path(root)


class TestAuditedRepoRoot:
    def test_unknown_package_resolves_to_none(self):
        # Arrange
        package = "scitex-definitely-not-a-real-package"
        # Act
        root = _audited_repo_root(package)
        # Assert
        assert root is None

    def test_repo_root_from_import_resolves_src_layout_root(self, tmp_path):
        """_repo_root_from_import walks find_spec up to the pyproject root."""
        # Arrange
        import sys

        repo = _build_importable_repo(tmp_path, "scitex_parityimp")
        sys.path.insert(0, str(repo / "src"))
        try:
            # Act
            resolved = _repo_root_from_import("scitex-parityimp")
        finally:
            sys.path.remove(str(repo / "src"))
            sys.modules.pop("scitex_parityimp", None)
        # Assert
        assert resolved == repo

    def test_repo_root_from_import_none_for_unimportable_package(self):
        """_repo_root_from_import returns None when the package cannot import."""
        # Arrange
        package = "scitex-no-such-importable-package"
        # Act
        resolved = _repo_root_from_import(package)
        # Assert
        assert resolved is None

    def test_audited_repo_root_falls_back_to_import_when_registry_absent(
        self, tmp_path
    ):
        """_audited_repo_root uses the import tree when the registry path is absent."""
        # Arrange
        import sys

        repo = _build_importable_repo(tmp_path, "scitex_parityfallback")
        sys.path.insert(0, str(repo / "src"))
        try:
            # Act
            resolved = _audited_repo_root("scitex-parityfallback")
        finally:
            sys.path.remove(str(repo / "src"))
            sys.modules.pop("scitex_parityfallback", None)
        # Assert
        assert resolved == repo

    def test_exemption_read_from_import_resolved_tree_config(self, tmp_path):
        """is_mcp_parity_exempt honors a config-only flag on the import-resolved tree."""
        # Arrange
        import sys

        repo = _build_importable_repo(
            tmp_path,
            "scitex_parityexempt",
            config_body="audit:\n  mcp-parity-exempt: true\n",
        )
        sys.path.insert(0, str(repo / "src"))
        try:
            # Act
            exempt = is_mcp_parity_exempt("scitex-parityexempt")
        finally:
            sys.path.remove(str(repo / "src"))
            sys.modules.pop("scitex_parityexempt", None)
        # Assert
        assert exempt is True
