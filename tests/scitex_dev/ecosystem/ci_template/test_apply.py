"""Behavioural tests for ``scitex_dev.ecosystem.ci_template.apply``.

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


# --------------------------------------------------------------------------- #
# Render — placeholder substitution
# --------------------------------------------------------------------------- #


def test_render_substitutes_pkg_name_and_module():
    # Arrange + Act
    body = render(
        "pr-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.11", "3.12", "3.13"],
        scripts={},
    )
    # Assert — both forms substituted; no placeholder remains
    assert "scitex-io" in body
    assert "scitex_io" in body
    assert "<PKG_NAME>" not in body
    assert "<PKG_MODULE>" not in body


def test_render_substitutes_python_versions_as_json_list():
    # Arrange + Act
    body = render(
        "pr-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.12"],
        scripts={},
    )
    # Assert
    assert '["3.12"]' in body
    assert "<PYTHON_VERSIONS_JSON>" not in body


def test_render_emits_cli_help_block_per_script_entry():
    # Arrange + Act
    body = render(
        "pr-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.12"],
        scripts={"scitex-io": "scitex_io._cli:main"},
    )
    # Assert
    assert "smoke scitex-io --help" in body


def test_render_drops_help_block_line_when_no_scripts():
    # Arrange + Act
    body = render(
        "pr-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.12"],
        scripts={},
    )
    # Assert — placeholder line removed entirely
    assert "<CLI_HELP_BLOCK>" not in body


# --------------------------------------------------------------------------- #
# Emitted job names — deterministic + drift-protected
# --------------------------------------------------------------------------- #


def test_emitted_job_names_is_deterministic_for_fixed_matrix():
    # Arrange + Act
    a = emitted_job_names(["3.11", "3.12", "3.13"])
    b = emitted_job_names(["3.11", "3.12", "3.13"])
    # Assert
    assert a == b
    assert "pytest-matrix-on-ubuntu-py3.11" in a
    assert "pytest-matrix-on-ubuntu-py3.12" in a
    assert "pytest-matrix-on-ubuntu-py3.13" in a
    assert "import-smoke-on-ubuntu-py3-12" in a
    assert "audit" in a


def test_emitted_job_names_scales_with_matrix():
    # Arrange + Act
    short = set(emitted_job_names(["3.12"]))
    long = set(emitted_job_names(["3.11", "3.12", "3.13"]))
    # Assert
    assert short < long
    assert "pytest-matrix-on-ubuntu-py3.11" not in short
    assert "pytest-matrix-on-ubuntu-py3.11" in long


def test_rendered_templates_carry_the_static_emitted_names(tmp_path):
    # Drift guard for the non-matrix names: the gate's claim is only
    # meaningful if the rendered YAML really does carry these `name:`
    # fields. Matrix names use `${{ matrix.python-version }}` and are
    # checked separately by `test_rendered_templates_carry_matrix_name`.
    # Arrange
    pvs = ["3.11", "3.12", "3.13"]
    body_pr = render(
        "pr-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=pvs,
        scripts={},
    )
    body_rel = render(
        "release-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=pvs,
        scripts={},
    )
    combined = body_pr + "\n" + body_rel
    # Assert — static names in the gate set really do show up
    for n in ("audit", "dep-hygiene-smoke", "import-smoke-on-ubuntu-py3-12"):
        assert n in combined, f"expected job name {n!r} not found in rendered templates"


def test_rendered_templates_carry_matrix_name_and_versions():
    # The matrix `name:` is `pytest-matrix-on-ubuntu-py${{ matrix.python-version }}`
    # and the matrix block carries the literal versions, so GitHub will
    # publish e.g. `pytest-matrix-on-ubuntu-py3.11`. Assert BOTH halves.
    # Arrange + Act
    body = render(
        "release-ci.yml.tmpl",
        pkg_name="scitex-io",
        pkg_module="scitex_io",
        python_versions=["3.11", "3.12", "3.13"],
        scripts={},
    )
    # Assert
    assert "pytest-matrix-on-ubuntu-py${{ matrix.python-version }}" in body
    assert '["3.11", "3.12", "3.13"]' in body


# --------------------------------------------------------------------------- #
# Branch-protection gate
# --------------------------------------------------------------------------- #


def test_gate_blocks_when_required_context_not_in_emitted_set(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)

    def lookup(_owner_repo, branch):
        if branch == "develop":
            return ["pytest-matrix-on-ubuntu-py3.11", "old-removed-check"]
        return []

    # Act + Assert
    with pytest.raises(BranchProtectionGateError) as exc_info:
        apply(
            repo,
            dry_run=True,
            owner_repo_lookup=_stub_owner_repo,
            required_contexts_lookup=lookup,
        )
    assert "old-removed-check" in str(exc_info.value)


def test_gate_passes_when_required_context_is_subset_of_emitted(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)

    def lookup(_owner_repo, branch):
        if branch == "develop":
            return ["pytest-matrix-on-ubuntu-py3.12", "audit"]
        return []

    # Act — does not raise
    result = apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=lookup,
    )
    # Assert
    assert result.required_contexts.get("develop") == [
        "pytest-matrix-on-ubuntu-py3.12",
        "audit",
    ]


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
    # Arrange — owner_repo resolves but no contexts are returned
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
    after = sorted(p.name for p in wf_dir.iterdir())
    assert before == after


def test_live_apply_writes_pr_ci_and_release_ci(tmp_path):
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
    wf_dir = repo / ".github" / "workflows"
    assert (wf_dir / "pr-ci.yml").is_file()
    assert (wf_dir / "release-ci.yml").is_file()
    content = (wf_dir / "pr-ci.yml").read_text()
    assert "<PKG_NAME>" not in content
    assert "scitex-fake" in content


def test_live_apply_deletes_consolidated_standalone_workflows(tmp_path):
    # Arrange — seed with a workflow that matches a delete prefix
    extra = {
        "import-smoke-on-ubuntu-py3-11.yml": "name: stub\n",
        "pytest-matrix-on-ubuntu-py3-11.yml": "name: stub\n",
        "dep-hygiene-smoke.yml": "name: stub\n",
    }
    repo = _make_repo(tmp_path, extra_workflows=extra)
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    wf_dir = repo / ".github" / "workflows"
    for name in extra:
        assert not (wf_dir / name).exists(), f"{name} should have been deleted"


def test_live_apply_preserves_cla_and_publish_workflows(tmp_path):
    # Arrange
    extra = {
        "cla.yml": "name: cla\n",
        "pypi-publish-and-github-release-on-tag.yml": "name: pub\n",
        "rtd-sphinx-build-on-ubuntu-latest.yml": "name: rtd\n",
        "auto-merge-to-develop.yaml": "name: am\n",
    }
    repo = _make_repo(tmp_path, extra_workflows=extra)
    # Act
    apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )
    # Assert
    wf_dir = repo / ".github" / "workflows"
    for name in extra:
        assert (wf_dir / name).is_file(), f"{name} must be preserved"


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
    wf_dir = repo / ".github" / "workflows"
    assert (wf_dir / "custom-operator-thing.yml").is_file()


# --------------------------------------------------------------------------- #
# Misc — error paths
# --------------------------------------------------------------------------- #


def test_apply_raises_on_missing_pyproject(tmp_path):
    # Arrange — git repo but no pyproject.toml
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    # Act + Assert
    with pytest.raises(ApplyError):
        apply(
            repo,
            dry_run=True,
            owner_repo_lookup=_stub_owner_repo,
            required_contexts_lookup=_stub_no_protection,
        )


def test_apply_raises_on_non_git_repo(tmp_path):
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n')
    # Act + Assert
    with pytest.raises(ApplyError):
        apply(
            repo,
            dry_run=True,
            owner_repo_lookup=_stub_owner_repo,
            required_contexts_lookup=_stub_no_protection,
        )


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
    pr = (repo / ".github" / "workflows" / "pr-ci.yml").read_text()
    rel = (repo / ".github" / "workflows" / "release-ci.yml").read_text()
    # Assert — both parse
    parsed_pr = yaml.safe_load(pr)
    parsed_rel = yaml.safe_load(rel)
    assert parsed_pr["name"] == "pr-ci"
    assert parsed_rel["name"] == "release-ci"
    # And jobs include the expected gate names
    assert "tests" in parsed_pr["jobs"]
    assert "audit" in parsed_pr["jobs"]
