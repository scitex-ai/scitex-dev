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

WHAT CHANGED 2026-08-05, recorded rather than quietly absorbed
--------------------------------------------------------------
PS-224 now accepts GitHub-hosted runners (operator ruling; さいXXX.md updated
to match). So the 2026-07-28 leftover — a `runs-on: ubuntu-latest` workflow —
is NO LONGER a violation. Two consequences worth stating plainly, because a
reader arriving later will otherwise mis-read these tests:

1. `test_applied_tree_has_zero_ps224_violations` still asserts the right
   property, but it can no longer FAIL for the original reason. Under the new
   rule the leftover would grade clean even if apply left it behind. What
   still protects that scenario is
   `test_legacy_rtd_workflow_is_gone_after_apply`, which is policy-independent.
2. The positive control was rewritten. It used to assert that the pre-apply
   tree contained exactly one violation — using `ubuntu-latest` as its known
   violation. That went to zero the moment hosted runners became legal, which
   is the control doing its job: it reported that its own proof-of-detection
   had been legislated away. It now uses an unregistered SELF-HOSTED pool,
   which is an error under both the old and the new rule.

The lesson is general and belongs here: a positive control must assert on the
most STABLE known-bad case available, never on the one the surrounding policy
debate is about.

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


#: A destination that is unregistered under BOTH the old and the new rule:
#: a self-hosted pool no runner advertises. `_is_github_hosted` matches only
#: a LONE hosted label, so this combination can never be waved through as a
#: hosted image. That stability is why the positive control uses it.
_UNREGISTERED_POOL_WF = """\
name: nightly
on: [push]
jobs:
  heavy:
    runs-on: [self-hosted, Linux, X64, pool-that-no-runner-advertises]
    steps:
      - uses: actions/checkout@v4
"""


def _make_repo_with_unregistered_pool(tmp_path: Path) -> Path:
    """A minimal repo whose only workflow targets an unregistered pool.

    Separate from `_make_repo` on purpose — see the control's comment.
    """
    repo = tmp_path / "control-repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "scitex-fake"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "nightly.yml").write_text(_UNREGISTERED_POOL_WF, encoding="utf-8")
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


def test_checker_detects_an_unregistered_destination_at_all(tmp_path):
    # POSITIVE CONTROL. Without it, a checker that silently graded nothing
    # (empty registry, hidden `.github`, unreadable tree) would report the
    # same clean zero as a genuine fix — "could not check" rendered as
    # "passed". Prove the checker DOES see a violation.
    #
    # It uses an UNREGISTERED SELF-HOSTED pool rather than `ubuntu-latest`,
    # and that choice is the whole point of this rewrite. The control
    # previously pointed at `ubuntu-latest`, which this branch legalises —
    # so the control went to zero and reported, correctly, that its own
    # proof-of-detection had been legislated away. A control must assert on
    # the most STABLE known violation available, never on the one currently
    # under debate.
    #
    # An unregistered self-hosted label is still an error under BOTH the old
    # and the new rule (`_is_github_hosted` matches only a lone hosted
    # label), so this control is policy-independent by construction.
    #
    # Its own tree, not `_make_repo`: adding this workflow to the shared
    # fixture would make `test_applied_tree_has_zero_ps224_violations` fail,
    # since `apply` has no reason to delete an arbitrary workflow.
    # Arrange
    repo = _make_repo_with_unregistered_pool(tmp_path)
    registry = _registry(tmp_path)
    # Act
    found = _ps224(repo, registry)
    # Assert
    assert len(found) == 1


# EOF
