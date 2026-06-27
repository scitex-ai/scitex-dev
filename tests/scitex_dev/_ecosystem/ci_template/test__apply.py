"""Behavioural tests for ``scitex_dev._ecosystem.ci_template.apply``.

Each test follows AAA + asserts ONE observable property (STX-TQ002 /
STX-TQ007). No ``unittest.mock`` — the apply function exposes injection
seams (``required_contexts_lookup``, ``owner_repo_lookup``) for the gate
boundary, and we exercise everything else against a real ``tmp_path``
working tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._ecosystem.ci_template import (
    ApplyError,
    BranchProtectionGateError,
    apply,
    emitted_job_names,
    render,
)


# --------------------------------------------------------------------------- #
# Fixtures — fake target repo
# --------------------------------------------------------------------------- #


def _make_repo(
    tmp_path: Path,
    *,
    pkg_name: str = "scitex-fake",
    scripts: dict | None = None,
    extra_workflows: dict | None = None,
) -> Path:
    """Create a minimal git-shaped repo with pyproject + .github/workflows."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()  # presence-only — apply() doesn't shell into git here

    scripts_block = ""
    if scripts:
        scripts_block = "[project.scripts]\n" + "\n".join(
            f'{k} = "{v}"' for k, v in scripts.items()
        )
    (repo / "pyproject.toml").write_text(
        f"""[project]
name = "{pkg_name}"
version = "0.0.0"

{scripts_block}
""",
        encoding="utf-8",
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    for name, content in (extra_workflows or {}).items():
        (wf_dir / name).write_text(content, encoding="utf-8")
    return repo


def _stub_owner_repo(_repo_dir: Path) -> str | None:
    return "ywatanabe1989/scitex-fake"


def _stub_no_protection(_owner_repo: str, _branch: str) -> list[str]:
    return []


def _render_pr(**overrides):
    """Default-args render of the PR template — keeps each test single-assert."""
    kwargs = dict(
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.11", "3.12", "3.13"],
        scripts={},
    )
    kwargs.update(overrides)
    return render("pr-ci.yml.tmpl", **kwargs)


# --------------------------------------------------------------------------- #
# Render — placeholder substitution
# --------------------------------------------------------------------------- #


def test_render_substitutes_pkg_name():
    # Arrange
    expected = "scitex-io"
    # Act
    body = _render_pr()
    # Assert
    assert expected in body


def test_render_substitutes_pkg_module():
    # Arrange
    expected_module = "scitex_io"
    # Act
    body = _render_pr()
    # Assert
    assert expected_module in body


def test_render_leaves_no_pkg_name_placeholder():
    # Arrange
    placeholder = "<PKG_NAME>"
    # Act
    body = _render_pr()
    # Assert
    assert placeholder not in body


def test_render_leaves_no_pkg_module_placeholder():
    # Arrange
    placeholder = "<PKG_MODULE>"
    # Act
    body = _render_pr()
    # Assert
    assert placeholder not in body


def test_render_substitutes_python_versions_as_json_list():
    # Arrange
    expected = '["3.12"]'
    # Act
    body = _render_pr(python_versions=["3.12"])
    # Assert
    assert expected in body


def test_render_leaves_no_python_versions_placeholder():
    # Arrange
    placeholder = "<PYTHON_VERSIONS_JSON>"
    # Act
    body = _render_pr(python_versions=["3.12"])
    # Assert
    assert placeholder not in body


def test_render_emits_cli_help_block_per_script_entry():
    # Arrange
    scripts = {"scitex-io": "scitex_io._cli:main"}
    # Act
    body = _render_pr(scripts=scripts)
    # Assert
    assert "smoke scitex-io --help" in body


def test_render_drops_help_block_line_when_no_scripts():
    # Arrange
    placeholder = "<CLI_HELP_BLOCK>"
    # Act
    body = _render_pr(scripts={})
    # Assert
    assert placeholder not in body


# --------------------------------------------------------------------------- #
# Emitted job names — deterministic + drift-protected
# --------------------------------------------------------------------------- #


def test_emitted_job_names_is_deterministic_for_fixed_matrix():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    a = emitted_job_names(matrix)
    b = emitted_job_names(matrix)
    # Assert
    assert a == b


def test_emitted_job_names_includes_static_audit_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "audit" in names


def test_emitted_job_names_includes_import_smoke_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "import-smoke-on-ubuntu-py3-12" in names


def test_emitted_job_names_includes_per_matrix_pytest_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "pytest-matrix-on-ubuntu-py3.11" in names


def test_emitted_job_names_scales_with_matrix():
    # Arrange
    short = set(emitted_job_names(["3.12"]))
    # Act
    long_set = set(emitted_job_names(["3.11", "3.12", "3.13"]))
    # Assert
    assert short < long_set


def test_emitted_job_names_includes_preserved_workflow_names_by_default():
    # Arrange
    matrix = ["3.12"]
    # Act
    names = set(emitted_job_names(matrix))
    # Assert
    assert "CLAssistant" in names


def test_emitted_job_names_includes_sphinx_when_default():
    # Arrange
    matrix = ["3.12"]
    # Act
    names = set(emitted_job_names(matrix))
    # Assert
    assert "sphinx" in names


def test_emitted_job_names_excludes_preserved_when_flag_false():
    # Arrange
    matrix = ["3.12"]
    # Act
    names = set(emitted_job_names(matrix, include_preserved=False))
    # Assert
    assert "CLAssistant" not in names


def test_rendered_pr_template_carries_static_audit_name():
    # Arrange
    expected = "name: audit"
    # Act
    body = _render_pr()
    # Assert
    assert expected in body


def test_rendered_pr_template_carries_dep_hygiene_smoke_name():
    # Arrange
    expected = "name: dep-hygiene-smoke"
    # Act
    body = _render_pr()
    # Assert
    assert expected in body


def test_rendered_pr_audit_is_incremental_new_only_gate():
    # The PR audit gate must be INCREMENTAL (--new-only vs the PR base), not a
    # strict full-tree audit — else a PR is failed on inherited debt it did not
    # introduce. The --since ref MUST track GITHUB_BASE_REF so the fetched ref
    # and the diff ref always match (the scitex-genai PR15 regression was a
    # fetch-main / diff-develop mismatch).
    # Arrange
    needles = ("--new-only", '--since "origin/${GITHUB_BASE_REF:-develop}"')
    # Act
    body = _render_pr()
    # Assert
    assert all(n in body for n in needles)


def test_rendered_pr_audit_checkout_fetches_full_history():
    # --new-only stages a worktree at the base ref + needs the merge-base; a
    # shallow depth-1 checkout has no common ancestor and silently degrades to
    # a strict full audit. fetch-depth: 0 is the guard.
    # Arrange
    expected = "fetch-depth: 0"
    # Act
    body = _render_pr()
    # Assert
    assert expected in body


def test_rendered_release_template_carries_matrix_name_placeholder():
    # Arrange
    expected = "pytest-matrix-on-ubuntu-py${{ matrix.python-version }}"
    # Act
    body = render(
        "release-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.11", "3.12", "3.13"],
        scripts={},
    )
    # Assert
    assert expected in body


def test_rendered_release_template_carries_matrix_versions_literal():
    # Arrange
    expected_literal = '["3.11", "3.12", "3.13"]'
    # Act
    body = render(
        "release-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.11", "3.12", "3.13"],
        scripts={},
    )
    # Assert
    assert expected_literal in body


# --------------------------------------------------------------------------- #
# Branch-protection gate
# --------------------------------------------------------------------------- #


def test_gate_blocks_when_required_context_not_in_emitted_set(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)

    def lookup(_owner_repo, branch):
        return ["old-removed-check"] if branch == "develop" else []

    # Act
    call = lambda: apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=lookup,
    )
    # Assert
    with pytest.raises(BranchProtectionGateError):
        call()


def test_gate_passes_when_required_context_is_subset_of_emitted(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)

    def lookup(_owner_repo, branch):
        return ["audit"] if branch == "develop" else []

    # Act
    result = apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=lookup,
    )
    # Assert
    assert result.required_contexts.get("develop") == ["audit"]


def test_skip_gate_flag_bypasses_a_failing_gate(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)

    def lookup(_owner_repo, _branch):
        return ["totally-bogus-check"]

    # Act
    result = apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=lookup,
        skip_required_check_gate=True,
    )
    # Assert
    assert result.gate_skipped is True


def test_gate_silently_passes_when_no_protection(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    result = apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert result.required_contexts == {}


def test_poisoned_context_is_filtered_out():
    # Arrange — a context name that is actually a serialised 404 error body
    from scitex_dev._ecosystem.ci_template._apply import _is_poisoned_context
    poisoned = (
        '{"message":"Branch not protected",'
        '"documentation_url":"https://docs.github.com/rest/branches/'
        'branch-protection#get-status-checks-protection","status":"404"}'
    )
    # Act
    flagged = _is_poisoned_context(poisoned)
    # Assert
    assert flagged is True


def test_normal_context_is_not_flagged_as_poisoned():
    # Arrange
    from scitex_dev._ecosystem.ci_template._apply import _is_poisoned_context
    # Act
    flagged = _is_poisoned_context("pytest-matrix-on-ubuntu-py3.12")
    # Assert
    assert flagged is False


def test_gate_silently_passes_when_only_poisoned_context_recorded(tmp_path):
    # Arrange — simulate a legacy repo whose branch-protection contains
    # exactly one poisoned context (a captured 404 error body). The reader
    # must filter it out so the gate trivially passes.
    repo = _make_repo(tmp_path)
    poisoned = [
        '{"message":"Branch not protected",'
        '"documentation_url":"https://docs.github.com/rest/branches/'
        'branch-protection#get-status-checks-protection","status":"404"}'
    ]
    # Wire the poisoned context into the live reader path (not the
    # injection stub) so this test exercises the filter at the seam.
    from scitex_dev._ecosystem.ci_template import _apply as _apply_mod

    def fake_gh_api_get(endpoint):
        import json as _json
        return 0, _json.dumps({"contexts": poisoned})

    orig = _apply_mod._gh_api_get
    _apply_mod._gh_api_get = fake_gh_api_get
    # Act
    try:
        result = apply(
            repo,
            dry_run=True,
            owner_repo_lookup=_stub_owner_repo,
            # Use the live _read_required_contexts which calls _gh_api_get
            required_contexts_lookup=None,
        )
    finally:
        _apply_mod._gh_api_get = orig
    # Assert
    assert result.required_contexts == {}


# --------------------------------------------------------------------------- #
# Dry-run vs live write
# --------------------------------------------------------------------------- #


def test_dry_run_does_not_write_files(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    wf_dir = repo / ".github" / "workflows"
    before = sorted(p.name for p in wf_dir.iterdir())
    # Act
    apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert sorted(p.name for p in wf_dir.iterdir()) == before


def test_live_apply_writes_pr_ci(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "pr-ci.yml").is_file()


def test_live_apply_writes_release_ci(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "release-ci.yml").is_file()


def test_live_apply_substitutes_target_pkg_name_into_written_yaml(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    content = (repo / ".github" / "workflows" / "pr-ci.yml").read_text()
    assert "scitex-fake" in content


def test_live_apply_deletes_import_smoke_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"import-smoke-on-ubuntu-py3-11.yml": "name: stub\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert not (repo / ".github" / "workflows" / "import-smoke-on-ubuntu-py3-11.yml").exists()


def test_live_apply_deletes_pytest_matrix_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"pytest-matrix-on-ubuntu-py3-11.yml": "name: stub\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert not (repo / ".github" / "workflows" / "pytest-matrix-on-ubuntu-py3-11.yml").exists()


def test_live_apply_deletes_dep_hygiene_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"dep-hygiene-smoke.yml": "name: stub\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert not (repo / ".github" / "workflows" / "dep-hygiene-smoke.yml").exists()


def test_live_apply_preserves_cla_workflow(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, extra_workflows={"cla.yml": "name: cla\n"})
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "cla.yml").is_file()


def test_live_apply_preserves_publish_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"pypi-publish-and-github-release-on-tag.yml": "name: pub\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "pypi-publish-and-github-release-on-tag.yml").is_file()


def test_live_apply_preserves_rtd_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"rtd-sphinx-build-on-ubuntu-latest.yml": "name: rtd\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "rtd-sphinx-build-on-ubuntu-latest.yml").is_file()


def test_live_apply_preserves_auto_merge_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"auto-merge-to-develop.yaml": "name: am\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "auto-merge-to-develop.yaml").is_file()


def test_live_apply_skips_unknown_workflow_names(tmp_path):
    # Arrange — a workflow not on the delete prefix list MUST be left alone
    repo = _make_repo(
        tmp_path,
        extra_workflows={"custom-operator-thing.yml": "name: custom\n"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    assert (repo / ".github" / "workflows" / "custom-operator-thing.yml").is_file()


# --------------------------------------------------------------------------- #
# Misc — error paths
# --------------------------------------------------------------------------- #


def test_apply_raises_on_missing_pyproject(tmp_path):
    # Arrange — git repo but no pyproject.toml
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    # Act
    call = lambda: apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    with pytest.raises(ApplyError):
        call()


def test_apply_raises_on_non_git_repo(tmp_path):
    # Arrange — pyproject present but no .git
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    # Act
    call = lambda: apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    with pytest.raises(ApplyError):
        call()


def test_rendered_yaml_is_parseable_yaml(tmp_path):
    # Arrange
    pytest.importorskip("yaml")
    import yaml

    repo = _make_repo(
        tmp_path,
        scripts={"scitex-fake": "scitex_fake._cli:main"},
    )
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    parsed = yaml.safe_load(
        (repo / ".github" / "workflows" / "pr-ci.yml").read_text()
    )
    # Assert
    assert parsed["name"] == "pr-ci"
