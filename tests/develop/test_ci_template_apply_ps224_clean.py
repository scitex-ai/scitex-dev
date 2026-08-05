"""End-to-end: `ci-template apply` must not MANUFACTURE a PS-224 violation.

Cross-cutting by construction — it drives the `_ecosystem.ci_template`
applier and then grades the resulting tree with the `_cli.audit._project`
PS-224 checker, so it mirrors no single src module and lives here rather
than under `tests/scitex_dev/` (PS-204 orphan-test placement).

The defect it pins, measured on a live fleet migration 2026-07-28: apply
shielded `rtd-sphinx-*` from deletion, so after a SUCCESSFUL apply the repo
still carried `rtd-sphinx-build-on-ubuntu-latest.yml` — `runs-on:
ubuntu-latest`, a leftover the tool itself guaranteed on EVERY repo and then
handed to a human to delete by hand. Asserting only "the file is gone" would
re-pin the old premise from the other side; grading the whole resulting tree
with the real checker is the property that actually matters.

WHAT CHANGED 2026-08-05, and why the two assertions now carry different
weights. That leftover WAS a PS-224 ERROR, which is why one checker could
carry both properties. PS-224 has since been narrowed to SELF-HOSTED
destinations — GitHub serves its own images, so a hosted job cannot queue
forever, the only failure PS-224 catches — and hosted runners are permitted
outright. So the historical leftover is no longer a PS-224 violation at all:

  * `test_legacy_rtd_workflow_is_gone_after_apply` now carries the 2026-07-28
    incident. A superseded file left behind is still a defect on its own
    terms, independent of any runner policy.
  * `test_applied_tree_has_zero_ps224_violations` carries tree cleanliness
    under CURRENT rules, and its positive control had to move to a separate
    probe tree — see `test_checker_fires_on_an_unserved_destination`.

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


#: A destination NO registered machine serves — the shape PS-224 still
#: errors on after the 2026-08-05 narrowing.
_UNSERVED_POOL = """\
name: probe
on: [push]
jobs:
  build:
    runs-on: [self-hosted, Linux, X64, pool-that-no-runner-advertises]
    steps:
      - uses: actions/checkout@v4
"""


def test_checker_fires_on_an_unserved_destination(tmp_path):
    # POSITIVE CONTROL — instrument liveness, not a claim about apply.
    # Without it, a checker that silently graded nothing (empty registry,
    # hidden `.github`, unreadable tree) would report the same clean zero as
    # a genuine fix — "could not check" rendered as "passed".
    #
    # It probes a SEPARATE tree rather than the pre-apply repo. Until
    # 2026-08-05 the pre-apply repo served as its own control, because the
    # legacy `rtd-sphinx-build-on-ubuntu-latest.yml` leftover was itself a
    # PS-224 error. PS-224 was then narrowed to SELF-HOSTED destinations —
    # GitHub serves its own images, so such a job cannot queue forever, the
    # only failure PS-224 catches — and that control silently went to zero.
    # It would have passed while proving nothing, which is the exact failure
    # mode it exists to prevent. Keep this pointed at a destination that is
    # genuinely unserved TODAY.
    # Arrange
    repo = tmp_path / "probe-repo"
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "probe.yml").write_text(
        _UNSERVED_POOL, encoding="utf-8"
    )
    registry = _registry(tmp_path)
    # Act
    found = _ps224(repo, registry)
    # Assert
    assert len(found) == 1


# EOF
