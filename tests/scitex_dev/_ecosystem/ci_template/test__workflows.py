"""Unit tests for the ci-template workflow-housekeeping policy.

Covers the two defects measured on a live fleet migration, 2026-07-28:

* **Stale protected prefix** — `rtd-sphinx-*` was shielded from deletion
  even though the emitted thin `ci.yml` carries a superseding
  `rtd-sphinx-build` caller job, so every "successful" apply left a
  `runs-on: ubuntu-latest` file behind (a PS-224 ERROR the tool itself
  manufactured). Protection is now lifted per-prefix, and ONLY when the
  rendered body genuinely declares the replacement job.

* **Under-reported blast radius** — protected files appeared in NO bucket,
  so "considered and deliberately kept" was rendered as the same silence as
  "never looked at". The invariant worth testing is the SUM: every file in
  `.github/workflows/` lands in exactly one of written / deleted /
  protected / skipped, and the union equals the directory listing.

No mocks (STX-NM002): everything runs against real `tmp_path` trees and
real value arguments through the existing seams.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._ecosystem.ci_template import (
    apply,
    eligible_for_delete,
    plan_workflow_changes,
    superseded_protected_prefixes,
)
from scitex_dev._ecosystem.ci_template._workflows import list_workflows

#: A rendered ci.yml body that DOES carry the superseding rtd job.
_CI_WITH_RTD = """\
name: ci
jobs:
  pytest-matrix:
    uses: scitex-ai/.github/.github/workflows/pytest-matrix.yml@main
  rtd-sphinx-build:
    uses: scitex-ai/.github/.github/workflows/rtd-sphinx-build.yml@main
"""

#: ...and one that does not.
_CI_WITHOUT_RTD = """\
name: ci
jobs:
  pytest-matrix:
    uses: scitex-ai/.github/.github/workflows/pytest-matrix.yml@main
"""

#: A mixed directory: legacy (deletable), protected, superseded-protected,
#: and an operator-owned unknown file.
_MIXED_WORKFLOWS = {
    "ci.yml": "name: old\n",
    "pr-ci.yml": "name: legacy\n",
    "pytest-matrix-on-ubuntu-py3-11.yml": "name: legacy\n",
    "rtd-sphinx-build-on-ubuntu-latest.yml": "name: rtd\n",
    "pypi-publish-and-github-release-on-tag.yml": "name: publish\n",
    "cla.yml": "name: cla\n",
    "custom-operator-thing.yml": "name: custom\n",
}


def _make_repo(tmp_path: Path, workflows: dict) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-fake"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    for name, body in workflows.items():
        (wf_dir / name).write_text(body, encoding="utf-8")
    return repo


def _dry_run(repo: Path):
    return apply(
        repo,
        dry_run=True,
        owner_repo_lookup=lambda _d: "ywatanabe1989/scitex-fake",
        required_contexts_lookup=lambda _o, _b: [],
    )


# --------------------------------------------------------------------------- #
# DEFECT 1 — protection is lifted only by a genuine superseding caller job
# --------------------------------------------------------------------------- #


def test_rtd_prefix_is_superseded_when_ci_yml_declares_the_job():
    # Arrange
    rendered = {".github/workflows/ci.yml": _CI_WITH_RTD}
    # Act
    superseded = superseded_protected_prefixes(rendered)
    # Assert
    assert "rtd-sphinx-" in superseded


def test_rtd_prefix_is_not_superseded_when_ci_yml_omits_the_job():
    # Arrange
    rendered = {".github/workflows/ci.yml": _CI_WITHOUT_RTD}
    # Act
    superseded = superseded_protected_prefixes(rendered)
    # Assert
    assert superseded == ()


def test_unparseable_ci_body_supersedes_nothing():
    # The safe direction: a body we cannot read must not be credited with
    # replacing anything, so every protection stays in force.
    # Arrange
    rendered = {".github/workflows/ci.yml": "name: ci\n  jobs: [broken\n"}
    # Act
    superseded = superseded_protected_prefixes(rendered)
    # Assert
    assert superseded == ()


def test_job_named_only_in_a_comment_does_not_supersede():
    # The shipped template LISTS the required contexts in its comment header;
    # a string match would read that as an emitted job.
    # Arrange
    rendered = {
        ".github/workflows/ci.yml": (
            "# contexts: rtd-sphinx-build / docs-sphinx\n"
            "name: ci\njobs:\n  pytest-matrix:\n    uses: x@main\n"
        )
    }
    # Act
    superseded = superseded_protected_prefixes(rendered)
    # Assert
    assert superseded == ()


def test_pypi_publish_stays_protected_even_under_supersession():
    # Genuinely non-superseded: the thin caller emits no publish job.
    # Arrange
    name = "pypi-publish-and-github-release-on-tag.yml"
    # Act
    deletable = eligible_for_delete(name, superseded_prefixes=("rtd-sphinx-",))
    # Assert
    assert deletable is False


def test_rtd_file_is_deletable_once_its_prefix_is_superseded():
    # Arrange
    name = "rtd-sphinx-build-on-ubuntu-latest.yml"
    # Act
    deletable = eligible_for_delete(name, superseded_prefixes=("rtd-sphinx-",))
    # Assert
    assert deletable is True


# --------------------------------------------------------------------------- #
# DEFECT 2 — the buckets PARTITION the workflow directory
# --------------------------------------------------------------------------- #


def test_buckets_union_equals_the_workflow_directory_listing(tmp_path):
    # Arrange — legacy + protected + superseded-protected + unknown, plus a
    # pre-existing ci.yml so the listing and the buckets are directly
    # comparable.
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    listing = set(list_workflows(repo))
    # Act
    result = _dry_run(repo)
    union = (
        set(result.written_paths)
        | set(result.deleted_paths)
        | set(result.protected_paths)
        | set(result.skipped_delete_paths)
    )
    # Assert
    assert union == listing


def test_buckets_are_pairwise_disjoint(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    # Act
    result = _dry_run(repo)
    buckets = [
        result.written_paths,
        result.deleted_paths,
        result.protected_paths,
        result.skipped_delete_paths,
    ]
    total = sum(len(b) for b in buckets)
    # Assert
    assert total == len({p for b in buckets for p in b})


def test_every_kept_file_carries_a_stated_reason(tmp_path):
    # "Kept" with no reason is the silence this defect was about.
    # Arrange
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    # Act
    result = _dry_run(repo)
    unreasoned = [p for p in result.kept_paths if not result.kept_reasons.get(str(p))]
    # Assert
    assert unreasoned == []


def test_protected_files_are_reported_not_omitted(tmp_path):
    # Previously they appeared in NO bucket at all.
    # Arrange
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    # Act
    result = _dry_run(repo)
    names = {p.name for p in result.protected_paths}
    # Assert
    assert {"cla.yml", "pypi-publish-and-github-release-on-tag.yml"} <= names


def test_superseded_rtd_file_is_reported_as_deleted_not_protected(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    # Act
    result = _dry_run(repo)
    # Assert
    assert "rtd-sphinx-build-on-ubuntu-latest.yml" in {
        p.name for p in result.deleted_paths
    }


def test_unknown_operator_workflow_lands_in_skipped(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    # Act
    result = _dry_run(repo)
    # Assert
    assert "custom-operator-thing.yml" in {
        p.name for p in result.skipped_delete_paths
    }


def test_plan_excludes_the_file_being_written(tmp_path):
    # ci.yml is the caller's WRITTEN bucket; it must not double-count as kept.
    # Arrange
    repo = _make_repo(tmp_path, _MIXED_WORKFLOWS)
    ci = repo / ".github" / "workflows" / "ci.yml"
    # Act
    plan = plan_workflow_changes(list_workflows(repo), rendered_paths=[ci])
    # Assert
    assert ci not in (plan.to_delete + plan.protected + plan.skipped)


# EOF
