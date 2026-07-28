"""End-to-end: `ci-template apply` must not MANUFACTURE a PS-224 violation.

Cross-cutting by construction — it drives the `_ecosystem.ci_template`
applier and then grades the resulting tree with the `_cli.audit._project`
PS-224 checker, so it mirrors no single src module and lives here rather
than under `tests/scitex_dev/` (PS-204 orphan-test placement).

The defect it pins, measured on a live fleet migration 2026-07-28: apply
shielded `rtd-sphinx-*` from deletion, so after a SUCCESSFUL apply the repo
still carried `rtd-sphinx-build-on-ubuntu-latest.yml` — `runs-on:
ubuntu-latest`, a PS-224 ERROR that the tool itself guaranteed on EVERY repo
and then handed to a human to delete by hand. Asserting only "the file is
gone" would re-pin the old premise from the other side; grading the whole
resulting tree with the real checker is the property that actually matters.

No mocks (STX-NM002): a real `tmp_path` repo tree, a real `hosts.yaml`
passed through the checker's existing `hosts_path=` file-path seam, and the
applier's existing `owner_repo_lookup` / `required_contexts_lookup` value
seams. Nothing is patched.
"""

from __future__ import annotations

from pathlib import Path

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._violation import Violation
from scitex_dev._ecosystem.ci_template import apply

#: A real registry recording the fleet's self-hosted label set. The emitted
#: ci.yml delegates via `uses:` and carries no `runs-on` of its own, so this
#: only has to be non-empty for the checker to grade rather than bail.
_REGISTRY = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, scitex-ci]
"""

#: The exact leftover a human had to delete by hand after a "successful"
#: apply (matching what the repo's own develop branch did in its merged PR).
_LEGACY_RTD = """\
name: rtd-sphinx-build
on: [push]
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-fake"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "rtd-sphinx-build-on-ubuntu-latest.yml").write_text(
        _LEGACY_RTD, encoding="utf-8"
    )
    return repo


def _registry(tmp_path: Path) -> Path:
    path = tmp_path / "hosts.yaml"
    path.write_text(_REGISTRY, encoding="utf-8")
    return path


def _apply_live(repo: Path):
    return apply(
        repo,
        dry_run=False,
        owner_repo_lookup=lambda _d: "scitex-ai/scitex-fake",
        required_contexts_lookup=lambda _o, _b: [],
    )


def _ps224(repo: Path, registry: Path) -> list:
    found: list = []
    check_ps224_runner_destinations(
        repo, Violation, found, hosts_path=registry
    )
    return found


def test_legacy_rtd_workflow_is_gone_after_apply(tmp_path):
    # Arrange
    repo = _make_repo(tmp_path)
    target = repo / ".github" / "workflows" / "rtd-sphinx-build-on-ubuntu-latest.yml"
    # Act
    _apply_live(repo)
    # Assert
    assert not target.exists()


def test_applied_tree_has_zero_ps224_violations(tmp_path):
    # THE end-to-end proof: the tool no longer manufactures the violation it
    # used to guarantee. Grading the whole tree (not just the one filename)
    # is what makes this a property rather than a restated implementation.
    # Arrange
    repo = _make_repo(tmp_path)
    registry = _registry(tmp_path)
    # Act
    _apply_live(repo)
    found = _ps224(repo, registry)
    # Assert
    assert found == []


def test_pre_apply_tree_is_the_violation_this_test_would_otherwise_miss(tmp_path):
    # POSITIVE CONTROL. Without it, a checker that silently graded nothing
    # (empty registry, hidden `.github`, unreadable tree) would report the
    # same clean zero as a genuine fix — "could not check" rendered as
    # "passed". Prove the checker DOES see this violation before apply.
    # Arrange
    repo = _make_repo(tmp_path)
    registry = _registry(tmp_path)
    # Act
    found = _ps224(repo, registry)
    # Assert
    assert len(found) == 1


# EOF
