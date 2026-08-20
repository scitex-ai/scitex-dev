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
    _tool_matches_api,
    declares_no_mcp,
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


# --------------------------------------------------------------------- #
# #82 — §6 must accept verb_<api> tools as matching single-token APIs   #
# --------------------------------------------------------------------- #
# Before this fix §2 (verb_noun tool naming) and §6 (Python-API coverage)
# could not BOTH be satisfied for single-token APIs (the SLURM verb
# family: sbatch / srun / squeue / sacct / scancel / salloc, plus sync /
# rsync). The fix lets §6 treat `submit_sbatch` as covering the API
# `sbatch`, so the package can keep §2-compliant tool names.


class TestSectionSixAcceptsVerbPrefixedTools:
    """#82 — single-token APIs satisfied by `<verb>_<api>` MCP tools."""

    def test_bare_name_match_still_counts(self):
        # Arrange
        tool, api = "save", "save"
        # Act
        result = _tool_matches_api(tool, api)
        # Assert
        assert result is True

    def test_verb_prefixed_tool_matches_single_token_api(self):
        # Arrange — submit_sbatch covers sbatch (#82 SLURM repro).
        tool, api = "submit_sbatch", "sbatch"
        # Act
        result = _tool_matches_api(tool, api)
        # Assert
        assert result is True

    def test_verb_prefixed_tool_does_not_falsely_match_unrelated_short_api(self):
        # Arrange — three corner cases that must all be checked together:
        # (a) trailing-letter overlap does NOT match (foo / o)
        # (b) the multi-token-API verb_<noun> form DOES match
        # (c) substring without a leading underscore does NOT match
        # Combined into one bool so the TQ007 'one assertion per test'
        # rule is satisfied while the three guards stay co-located.
        cases = (("foo", "o"), ("compute_metrics", "metrics"), ("sbatchwrapper", "sbatch"))
        # Act
        results = tuple(_tool_matches_api(t, a) for t, a in cases)
        # Assert
        assert results == (False, True, False), (
            "matcher boundaries: (foo,o)=False, (compute_metrics,metrics)=True, "
            f"(sbatchwrapper,sbatch)=False — got {results}"
        )

    def test_slurm_verb_apis_satisfied_by_verb_prefixed_tools(self):
        """The scitex-hpc#10 repro — sbatch/srun/sync covered by
        submit_sbatch / dispatch_srun / sync_project."""
        # Arrange — pretend scitex-hpc surface from the #82 issue body.
        py_apis = {
            "sbatch", "srun", "sync",
            "poll_job", "fetch_result", "detect_module_system",
            "module_load", "load_apptainer",
        }
        mcp_normalized = {
            "submit_sbatch", "dispatch_srun", "sync_project",
            "poll_job", "fetch_result", "detect_module_system",
            "module_load", "load_apptainer",
        }
        # Act
        violations = _parity_violations("scitex-hpc", py_apis, mcp_normalized)
        # Assert — no §6 violation: every API is covered, every tool maps.
        assert violations == [], (
            f"§6 should accept verb_<api> as a match (#82); got {violations}"
        )

    def test_verb_prefixed_tools_are_not_counted_as_orphans(self):
        """Symmetric direction — submit_sbatch isn't orphan when sbatch
        is in the Python API. Prevents the §6 orphan-tool tier from
        firing on the same scitex-hpc#10 scenario."""
        # Arrange — 5 verb_<api> tools (orphan threshold > 3), single
        # SLURM API. Without the fix the 5 verb_-prefixed tools would
        # all count as orphans (none == "sbatch") and trip §6.
        py_apis = {"sbatch"}
        mcp_normalized = {
            "submit_sbatch", "dispatch_sbatch", "queue_sbatch",
            "cancel_sbatch", "resubmit_sbatch",
        }
        # Act
        violations = _parity_violations("scitex-hpc", py_apis, mcp_normalized)
        # Assert
        assert violations == [], (
            f"orphan check should match verb_<api> too; got {violations}"
        )

    def test_genuine_orphan_still_trips_when_no_api_matches(self):
        """Guard rail — the fix must not silence true orphan-tool
        violations. 5 plotting tools with zero Python APIs still trip."""
        # Arrange
        py_apis: set[str] = set()
        mcp_normalized = {"plot", "scatter", "bar", "hist", "boxplot"}
        # Act
        violations = _parity_violations("plot-rich", py_apis, mcp_normalized)
        # Assert
        assert any(v.rule == "§6" for v in violations)


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

    def test_audited_tree_wins_over_registry_local_path(self, tmp_path):
        """The import-resolved (audited) tree outranks the registry local_path.

        Self-hosted CI runners often carry a stale ``~/proj/<pkg>`` checkout
        at the registry path; §6 exemptions must be read from the tree under
        audit (scitex-orochi #460), so the registry may only decide when no
        importable checkout exists.
        """
        # Arrange
        import sys

        repo = _build_importable_repo(tmp_path, "scitex_parityprecedence")
        stale = tmp_path / "stale-registry-checkout"
        stale.mkdir()
        (stale / "pyproject.toml").write_text(
            '[project]\nname = "scitex-parityprecedence"\nversion = "0.0.0"\n'
        )
        sys.path.insert(0, str(repo / "src"))
        try:
            # Act
            resolved = _audited_repo_root(
                "scitex-parityprecedence",
                registry_resolver=lambda pkg: stale,
            )
        finally:
            sys.path.remove(str(repo / "src"))
            sys.modules.pop("scitex_parityprecedence", None)
        # Assert
        assert resolved == repo

    def test_registry_local_path_decides_when_package_not_importable(
        self, tmp_path
    ):
        """Without an importable checkout, the registry local_path still resolves."""
        # Arrange
        registry_dir = tmp_path / "registry-checkout"
        registry_dir.mkdir()
        # Act
        resolved = _audited_repo_root(
            "scitex-no-such-importable-package",
            registry_resolver=lambda pkg: registry_dir,
        )
        # Assert
        assert resolved == registry_dir

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
            # repo=None is the POINT of this test: it asserts the discovery
            # path, so "I have no audited tree" is stated rather than defaulted.
            exempt = is_mcp_parity_exempt("scitex-parityexempt", repo=None)
        finally:
            sys.path.remove(str(repo / "src"))
            sys.modules.pop("scitex_parityexempt", None)
        # Assert
        assert exempt is True


# ---------------------------------------------------------------------------
# CAPABILITY knob -> no-mcp gates the §6 MCP <-> Python-API parity check.
# (Split out of the former _project/test__capability_knob.py orphan; the
# symbols under test live in this module's mirror src, _summary/_mcp_parity.py.)
# Operator directive 2026-06-22.
# ---------------------------------------------------------------------------


def _write_caps_config(repo: Path, capabilities: list[str] | None) -> None:
    """Write a `.scitex/dev/config.yaml` for `repo`, optionally with caps."""
    cfg_dir = repo / ".scitex" / "dev"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    body = "project-type:\n  - pip\n"
    if capabilities is not None:
        body += "audit:\n  capabilities:\n"
        for cap in capabilities:
            body += f"    - {cap}\n"
    (cfg_dir / "config.yaml").write_text(body, encoding="utf-8")


def _make_alias_repo(tmp_path: Path, capabilities: list[str] | None) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "scitex-plt"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    _write_caps_config(tmp_path, capabilities)
    return tmp_path


def test_declares_no_mcp_true_with_capability(tmp_path):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=["no-mcp"])
    # Act
    result = declares_no_mcp("scitex-plt", repo=repo)
    # Assert
    assert result is True


def test_declares_no_mcp_false_without_capability(tmp_path):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=None)
    # Act
    result = declares_no_mcp("scitex-plt", repo=repo)
    # Assert
    assert result is False


def test_parity_check_emits_no_violations_with_no_mcp(tmp_path):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=["no-mcp"])
    out: list = []
    # Act
    _check_api_parity("scitex-plt", {"plt_orphan_tool"}, out, repo=repo)
    # Assert
    assert out == []


def test_parity_check_emits_capability_notice_with_no_mcp(tmp_path, capsys):
    # Arrange
    repo = _make_alias_repo(tmp_path, capabilities=["no-mcp"])
    out: list = []
    # Act
    _check_api_parity("scitex-plt", {"plt_orphan_tool"}, out, repo=repo)
    # Assert
    assert "skipped (declared capability: no-mcp)" in capsys.readouterr().err
