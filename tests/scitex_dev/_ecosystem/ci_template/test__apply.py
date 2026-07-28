"""Behavioural tests for ``scitex_dev._ecosystem.ci_template.apply``.

Pins THE single canonical CI mechanism (operator decision, 2026-07-21):
one thin ``ci.yml`` caller delegating to ``scitex-ai/.github@main``,
runner selection via ``vars.CI_RUNS_ON`` with a self-hosted default,
never ubuntu-latest, superseded/newb-docs workflow cleanup.

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

#: The four org-level reusable workflows the caller must delegate to.
ORG_REUSABLE_USES = (
    "scitex-ai/.github/.github/workflows/pytest-matrix.yml@main",
    "scitex-ai/.github/.github/workflows/import-smoke.yml@main",
    "scitex-ai/.github/.github/workflows/quality-audit.yml@main",
    "scitex-ai/.github/.github/workflows/rtd-sphinx-build.yml@main",
)

#: The one sanctioned self-hosted runner default.
CI_RUNS_ON_DEFAULT = '["self-hosted","Linux","X64","scitex-ci"]'


# --------------------------------------------------------------------------- #
# Fixtures — fake target repo
# --------------------------------------------------------------------------- #


def _make_repo(
    tmp_path: Path,
    *,
    pkg_name: str = "scitex-fake",
    extra_workflows: dict | None = None,
) -> Path:
    """Create a minimal git-shaped repo with pyproject + .github/workflows."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()  # presence-only — apply() doesn't shell into git here

    (repo / "pyproject.toml").write_text(
        f"""[project]
name = "{pkg_name}"
version = "0.0.0"
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


def _render_ci(**overrides):
    """Default-args render of the caller template — keeps tests single-assert."""
    kwargs = dict(pkg_name="scitex-io", pkg_module="scitex_io")
    kwargs.update(overrides)
    return render("ci.yml.tmpl", **kwargs)


def _apply_live(repo: Path):
    return apply(
        repo,
        dry_run=False,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=_stub_no_protection,
    )


def _parse(body: str) -> dict:
    yaml = pytest.importorskip("yaml")
    # `on:` is the YAML boolean True key after safe_load — irrelevant here.
    return yaml.safe_load(body)


# --------------------------------------------------------------------------- #
# Render — placeholder substitution
# --------------------------------------------------------------------------- #


def test_render_substitutes_pkg_name():
    # Arrange
    expected = "scitex-io"
    # Act
    body = _render_ci()
    # Assert
    assert expected in body


def test_render_leaves_no_pkg_name_placeholder():
    # Arrange
    placeholder = "<PKG_NAME>"
    # Act
    body = _render_ci()
    # Assert
    assert placeholder not in body


def test_render_leaves_no_angle_bracket_placeholder_at_all():
    # Guard against a future template gaining a placeholder render() does
    # not substitute.
    # Arrange
    import re

    # Act
    body = _render_ci()
    leftovers = re.findall(r"<[A-Z_]+>", body)
    # Assert
    assert leftovers == []


# --------------------------------------------------------------------------- #
# Caller shape — thin org-reusable delegation, nothing else
# --------------------------------------------------------------------------- #


def test_caller_delegates_to_all_four_org_reusable_workflows():
    # Arrange
    expected_uses = ORG_REUSABLE_USES
    # Act
    body = _render_ci()
    # Assert
    assert all(u in body for u in expected_uses)


def test_caller_jobs_are_pure_uses_calls_with_inherited_secrets():
    # Every job must be a thin `uses:` + `secrets: inherit` pair — no local
    # steps, no runs-on (a caller job cannot set one), no second body that
    # could drift against the org-side workflows.
    # Arrange
    doc = _parse(_render_ci())
    # Act
    jobs = doc["jobs"].values()
    # Assert
    assert all(
        set(job) == {"uses", "secrets"}
        and job["secrets"] == "inherit"
        and job["uses"].startswith("scitex-ai/.github/.github/workflows/")
        and job["uses"].endswith("@main")
        for job in jobs
    )


def test_caller_job_ids_pin_required_status_check_prefixes():
    # Under workflow_call the check context is "<caller-job-id> / <job name>";
    # branch protection references these ids, so they must not drift.
    # Arrange
    expected = {"pytest-matrix", "import-smoke", "quality-audit", "rtd-sphinx-build"}
    # Act
    doc = _parse(_render_ci())
    # Assert
    assert set(doc["jobs"]) == expected


def test_caller_triggers_cover_pr_and_push_and_dispatch():
    # The single ci.yml replaces BOTH retired shapes: pr-ci (pull_request)
    # and release-ci (push to protected branches + schedule).
    # Arrange
    doc = _parse(_render_ci())
    # Act
    triggers = doc.get(True) or doc.get("on")  # yaml 1.1 parses `on:` as True
    # Assert
    assert {"pull_request", "push", "schedule", "workflow_dispatch"} <= set(triggers)


def test_caller_cancels_only_superseded_pr_runs():
    # Preserve the retired pair's semantics: cancel superseded PR runs,
    # never cancel post-merge/protected-branch validation.
    # Arrange
    doc = _parse(_render_ci())
    # Act
    cancel = doc["concurrency"]["cancel-in-progress"]
    # Assert
    assert cancel == "${{ github.event_name == 'pull_request' }}"


def test_caller_carries_ci_runs_on_runner_selection_contract():
    # Runner selection = Actions Variable CI_RUNS_ON resolved from the
    # caller repo (documented in the emitted body; enforced org-side).
    # Arrange
    expected = "vars.CI_RUNS_ON"
    # Act
    body = _render_ci()
    # Assert
    assert expected in body


def test_caller_carries_self_hosted_default_label_set():
    # Arrange
    expected = CI_RUNS_ON_DEFAULT
    # Act
    body = _render_ci()
    # Assert
    assert expected in body


def test_caller_never_mentions_ubuntu_latest():
    # PS-169: GitHub-hosted runners are forbidden — the emitted body must
    # not carry ubuntu-latest in any form, comment included.
    # Arrange
    forbidden = "ubuntu-latest"
    # Act
    body = _render_ci()
    # Assert
    assert forbidden not in body


def test_rendered_yaml_is_parseable_yaml():
    # Arrange
    body = _render_ci()
    # Act
    doc = _parse(body)
    # Assert
    assert doc["name"] == "ci"


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


def test_emitted_job_names_includes_quality_audit_caller_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "quality-audit / audit" in names


def test_emitted_job_names_includes_import_smoke_caller_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "import-smoke / import-smoke-on-ubuntu-py3-12" in names


def test_emitted_job_names_includes_rtd_sphinx_caller_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "rtd-sphinx-build / docs-sphinx" in names


def test_emitted_job_names_includes_per_matrix_pytest_context():
    # Arrange
    matrix = ["3.11", "3.12", "3.13"]
    # Act
    names = emitted_job_names(matrix)
    # Assert
    assert "pytest-matrix / pytest-matrix-on-ubuntu-py3.11" in names


def test_emitted_job_names_scales_with_matrix():
    # Arrange
    short = set(emitted_job_names(["3.12"]))
    # Act
    long_set = set(emitted_job_names(["3.11", "3.12", "3.13"]))
    # Assert
    assert short < long_set


def test_emitted_job_names_prefixes_match_caller_job_ids():
    # The gate's expected contexts and the template's caller-job ids are two
    # renderings of the same contract — pin them against each other.
    # Arrange
    doc = _parse(_render_ci())
    caller_ids = set(doc["jobs"])
    # Act
    prefixes = {
        n.split(" / ")[0]
        for n in emitted_job_names(["3.12"], include_preserved=False)
    }
    # Assert
    assert prefixes == caller_ids


def test_emitted_job_names_includes_preserved_workflow_names_by_default():
    # Arrange
    matrix = ["3.12"]
    # Act
    names = set(emitted_job_names(matrix))
    # Assert
    assert "CLAssistant" in names


def test_emitted_job_names_excludes_bare_sphinx_context():
    # INVERTED 2026-07-28 alongside the rtd-sphinx delete. The bare `sphinx`
    # / `docs` contexts came from `rtd-sphinx-*.yml`, which apply now DELETES
    # as superseded — so nothing publishes them after the migration. Listing
    # them as emitted would let the gate wave through exactly the deadlock it
    # exists to prevent (a repo requiring `sphinx` forever).
    # Arrange
    matrix = ["3.12"]
    # Act
    names = set(emitted_job_names(matrix))
    # Assert
    assert "sphinx" not in names


def test_emitted_job_names_excludes_preserved_when_flag_false():
    # Arrange
    matrix = ["3.12"]
    # Act
    names = set(emitted_job_names(matrix, include_preserved=False))
    # Assert
    assert "CLAssistant" not in names


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


def test_gate_blocks_on_stale_unprefixed_consolidated_contexts(tmp_path):
    # A repo still requiring the OLD consolidated context names (no caller
    # prefix) must be refused — branch protection needs updating first.
    # Arrange
    repo = _make_repo(tmp_path)

    def lookup(_owner_repo, branch):
        return ["audit"] if branch == "develop" else []

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
        return ["quality-audit / audit"] if branch == "develop" else []

    # Act
    result = apply(
        repo,
        dry_run=True,
        owner_repo_lookup=_stub_owner_repo,
        required_contexts_lookup=lookup,
    )
    # Assert
    assert result.required_contexts.get("develop") == ["quality-audit / audit"]


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
    flagged = _is_poisoned_context("pytest-matrix / pytest-matrix-on-ubuntu-py3.12")
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


def test_live_apply_writes_ci_yml(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    _apply_live(repo)
    # Assert
    assert (repo / ".github" / "workflows" / "ci.yml").is_file()


def test_live_apply_writes_only_one_workflow(tmp_path):
    # ONE canonical per-repo workflow — nothing else may be emitted.
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    result = _apply_live(repo)
    # Assert
    assert [p.name for p in result.written_paths] == ["ci.yml"]


def test_live_apply_substitutes_target_pkg_name_into_written_yaml(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    _apply_live(repo)
    # Assert
    content = (repo / ".github" / "workflows" / "ci.yml").read_text()
    assert "scitex-fake" in content


def test_live_apply_emits_no_ubuntu_latest_anywhere(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    # Act
    result = _apply_live(repo)
    # Assert — across every emitted body, not just ci.yml.
    assert all("ubuntu-latest" not in body for body in result.rendered.values())


def test_live_apply_deletes_superseded_pr_ci_workflow(tmp_path):
    # The retired consolidated pair is the LOSING mechanism's output —
    # apply must remove it so no second shape lingers.
    # Arrange
    repo = _make_repo(tmp_path, extra_workflows={"pr-ci.yml": "name: stub\n"})
    # Act
    _apply_live(repo)
    # Assert
    assert not (repo / ".github" / "workflows" / "pr-ci.yml").exists()


def test_live_apply_deletes_superseded_release_ci_workflow(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, extra_workflows={"release-ci.yml": "name: stub\n"})
    # Act
    _apply_live(repo)
    # Assert
    assert not (repo / ".github" / "workflows" / "release-ci.yml").exists()


def test_live_apply_deletes_newb_docs_workflow(tmp_path):
    # Operator-ordered fleet-wide removal: newb-docs is NOT part of the
    # canonical set and must be cleaned up like any superseded file.
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"newb-docs-quality-on-ubuntu-latest.yml": "name: stub\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert not (
        repo / ".github" / "workflows" / "newb-docs-quality-on-ubuntu-latest.yml"
    ).exists()


def test_live_apply_deletes_import_smoke_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"import-smoke-on-ubuntu-py3-11.yml": "name: stub\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert not (repo / ".github" / "workflows" / "import-smoke-on-ubuntu-py3-11.yml").exists()


def test_live_apply_deletes_pytest_matrix_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"pytest-matrix-on-ubuntu-py3-11.yml": "name: stub\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert not (repo / ".github" / "workflows" / "pytest-matrix-on-ubuntu-py3-11.yml").exists()


def test_live_apply_deletes_dep_hygiene_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"dep-hygiene-smoke.yml": "name: stub\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert not (repo / ".github" / "workflows" / "dep-hygiene-smoke.yml").exists()


def test_live_apply_deletes_quality_audit_standalone_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={
            "scitex-fake-quality-audit-on-ubuntu-latest.yml": "name: stub\n"
        },
    )
    # Act
    _apply_live(repo)
    # Assert
    assert not (
        repo / ".github" / "workflows"
        / "scitex-fake-quality-audit-on-ubuntu-latest.yml"
    ).exists()


def test_live_apply_preserves_cla_workflow(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, extra_workflows={"cla.yml": "name: cla\n"})
    # Act
    _apply_live(repo)
    # Assert
    assert (repo / ".github" / "workflows" / "cla.yml").is_file()


def test_live_apply_preserves_publish_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"pypi-publish-and-github-release-on-tag.yml": "name: pub\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert (repo / ".github" / "workflows" / "pypi-publish-and-github-release-on-tag.yml").is_file()


def test_live_apply_deletes_superseded_rtd_sphinx_workflow(tmp_path):
    # INVERTED 2026-07-28. `rtd-sphinx-*` was protected unconditionally on the
    # premise that the caller's rtd-sphinx-build job was "additive". It is not
    # — it does the same work org-side, so the standalone file is superseded.
    # Keeping it meant every migrated repo retained a `runs-on: ubuntu-latest`
    # workflow, i.e. a PS-224 ERROR the tool itself guaranteed and a human had
    # to delete by hand.
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"rtd-sphinx-build-on-ubuntu-latest.yml": "name: rtd\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert not (
        repo / ".github" / "workflows" / "rtd-sphinx-build-on-ubuntu-latest.yml"
    ).exists()


def test_rtd_sphinx_stays_protected_when_ci_yml_lacks_the_superseding_job():
    # The delete is CONDITIONAL, never blind: protection is lifted only
    # because the body being written declares `rtd-sphinx-build`. A template
    # that ever drops that job must re-protect the standalone files.
    # Arrange
    from scitex_dev._ecosystem.ci_template import eligible_for_delete
    body_without_rtd = "name: ci\njobs:\n  pytest-matrix:\n    uses: x@main\n"
    from scitex_dev._ecosystem.ci_template import superseded_protected_prefixes

    superseded = superseded_protected_prefixes(
        {".github/workflows/ci.yml": body_without_rtd}
    )
    # Act
    deletable = eligible_for_delete(
        "rtd-sphinx-build-on-ubuntu-latest.yml", superseded_prefixes=superseded
    )
    # Assert
    assert deletable is False


def test_live_apply_preserves_auto_merge_workflow(tmp_path):
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"auto-merge-to-develop.yaml": "name: am\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert (repo / ".github" / "workflows" / "auto-merge-to-develop.yaml").is_file()


def test_live_apply_skips_unknown_workflow_names(tmp_path):
    # Arrange — a workflow not on the delete prefix list MUST be left alone
    repo = _make_repo(
        tmp_path,
        extra_workflows={"custom-operator-thing.yml": "name: custom\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    assert (repo / ".github" / "workflows" / "custom-operator-thing.yml").is_file()


def test_live_apply_overwrites_existing_ci_yml_with_canonical_shape(tmp_path):
    # A pre-existing ci.yml (e.g. the retired in-SIF single-CI body) is
    # replaced in place by the canonical caller, never deleted-then-lost.
    # Arrange
    repo = _make_repo(
        tmp_path,
        extra_workflows={"ci.yml": "name: old-in-sif-body\n"},
    )
    # Act
    _apply_live(repo)
    # Assert
    content = (repo / ".github" / "workflows" / "ci.yml").read_text()
    assert "scitex-ai/.github/.github/workflows/pytest-matrix.yml@main" in content


def test_written_ci_yml_is_parseable_yaml(tmp_path):
    # Arrange
    yaml = pytest.importorskip("yaml")
    repo = _make_repo(tmp_path)
    # Act
    _apply_live(repo)
    parsed = yaml.safe_load(
        (repo / ".github" / "workflows" / "ci.yml").read_text()
    )
    # Assert
    assert parsed["name"] == "ci"


# --------------------------------------------------------------------------- #
# Single-mechanism invariant — no second template body may exist
# --------------------------------------------------------------------------- #


def test_templates_dir_ships_exactly_one_workflow_template():
    # The dual-canonical drift root cause was TWO template bodies. Pin the
    # vendored templates dir to exactly the one caller template.
    # Arrange
    from scitex_dev._ecosystem.ci_template import _apply as _apply_mod

    tdir = _apply_mod._templates_dir()
    # Act
    tmpl_names = sorted(p.name for p in tdir.iterdir() if p.is_file())
    # Assert
    assert tmpl_names == ["ci.yml.tmpl"]


def test_ci_runner_package_ships_no_workflow_template_body():
    # The losing mechanism (`ci runner register`'s in-SIF ci.yml.template)
    # must stay deleted — its templates dir may carry hooks, but no
    # GitHub-workflow YAML body that could drift against the canonical one.
    # Arrange
    import scitex_dev.ci.runner as runner_pkg

    tdir = Path(runner_pkg.__file__).parent / "templates"
    # Act
    workflow_bodies = [
        p.name
        for p in (tdir.iterdir() if tdir.is_dir() else [])
        if ".yml" in p.name or ".yaml" in p.name
    ]
    # Assert
    assert workflow_bodies == []


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
