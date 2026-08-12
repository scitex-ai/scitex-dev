"""PS-224 and the `sac-control-plane` destination — BOTH directions.

sac's CI feedback rail (PR #1005) adds a `verdict` job that must call
`sac listen` on `127.0.0.1:7878` and write a card to the store on
`127.0.0.1:55432`. Both bind LOOPBACK, and the org's four CI runners live on
four different machines, so only the runner co-located with those services
can do it — hence the pin to `sac-control-plane`. PS-224 refused that job
because the machine registry did not record the destination. The registry was
right: the label was real and carried by exactly one runner, but nothing
declared it. The fix is to DECLARE it (scitex-dev's shipped seed), never to
exempt the job — an exemption granted because a rule is inconvenient is how
an audit stops meaning anything.

A registration test that only proves the ACCEPT direction cannot tell
"registered the destination" from "stopped checking", so every accept case
here is paired with a reject case that must keep failing:

* `test_control_plane_destination_is_accepted`  — FAILS before the seed
  entry, passes after. This is the change under test.
* `test_unregistered_control_plane_lookalike_is_still_rejected` — passes
  before AND after. If the seed edit had widened the rule instead of adding
  one machine, this is the test that would go green when it must not.
* `test_control_plane_combined_with_a_foreign_label_is_still_rejected` —
  the labels are each served, but by DIFFERENT machines. GitHub would queue
  such a job forever, so the union must not flatten.

Every case runs against a user-state `hosts.yaml` that registers only an
UNRELATED machine, so an accepted destination can only have come from the
SHIPPED floor — which is the deployment that matters: a CI runner and a
container both have no fleet `hosts.yaml` of their own.

No mocks (NM001-003): a real repo tree under `tmp_path`, a real registry
file through the check's `hosts_path=` seam, the floor read as shipped.
One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._violation import Violation

#: A user-state registry that knows nothing about scitex-compute-04. Anything
#: accepted below is therefore accepted on the strength of the SHIPPED seed.
_REGISTRY_UNRELATED_ONLY = """\
hosts:
  ci-box:
    kind: workstation
    ssh_alias: ci-box
    scitex_root: "~/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, ci-box-local]
"""

#: Exactly what sac's `verdict` job pins, copied from PR #1005.
_CONTROL_PLANE = '[self-hosted, Linux, X64, sac-control-plane]'

#: A plausible neighbour that NO runner carries. The point of the name is
#: that it is one character from a registered one: the rule must reject on
#: what the registry says, not on what the label looks like.
_LOOKALIKE = "[self-hosted, Linux, X64, sac-control-plane-2]"

#: `sac-control-plane` (scitex-compute-04) and `spartan-cpu` (spartan) are
#: both served — by different machines. No single runner carries both.
_CROSS_MACHINE = "[self-hosted, Linux, X64, sac-control-plane, spartan-cpu]"


@pytest.fixture
def unrelated_registry(tmp_path) -> Path:
    """A real hosts.yaml registering only a machine the seed never mentions."""
    path = tmp_path / "hosts.yaml"
    path.write_text(_REGISTRY_UNRELATED_ONLY)
    return path


def _repo_with_workflow(tmp_path: Path, runs_on: str) -> Path:
    """Build a repo whose `.github/workflows/ci.yml` pins `runs_on`."""
    repo = tmp_path / "repo"
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "ci.yml").write_text(
        f"name: ci\non: [push]\njobs:\n  verdict:\n    runs-on: {runs_on}\n"
    )
    return repo


def _run(repo: Path, registry_path: Path) -> list[Violation]:
    out: list[Violation] = []
    check_ps224_runner_destinations(repo, Violation, out, hosts_path=registry_path)
    return out


# -------- ACCEPT: the destination this change registers --------------------


def test_control_plane_destination_is_accepted(tmp_path, unrelated_registry):
    # Arrange — the job sac's CI feedback rail actually ships. Before
    # scitex-compute-04 was registered this produced one E and blocked the PR.
    repo = _repo_with_workflow(tmp_path, _CONTROL_PLANE)
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert found == []


def test_the_whole_org_cpu_label_set_is_accepted_too(tmp_path, unrelated_registry):
    # Arrange — the runner's EFFECTIVE set is what was registered, so the
    # broader destination its siblings also serve resolves as well. Recording
    # `sac-control-plane` alone would have left this red.
    repo = _repo_with_workflow(tmp_path, "[self-hosted, Linux, X64, scitex-org-cpu]")
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert found == []


# -------- REJECT: the rule still refuses what nothing declares -------------


def test_unregistered_control_plane_lookalike_is_still_rejected(
    tmp_path, unrelated_registry
):
    # Arrange — the mutation proof for the accept case above. A seed edit
    # that widened PS-224 instead of adding one machine would turn this
    # green, and the accept test alone could not tell the difference.
    repo = _repo_with_workflow(tmp_path, _LOOKALIKE)
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert len(found) == 1


def test_the_lookalike_rejection_is_severity_error(tmp_path, unrelated_registry):
    # Arrange — E is the whole point of PS-224: W never affects the exit
    # code, so a W here would be an undeliverable job that still merges.
    repo = _repo_with_workflow(tmp_path, _LOOKALIKE)
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert found[0].severity == "E"


def test_control_plane_combined_with_a_foreign_label_is_still_rejected(
    tmp_path, unrelated_registry
):
    # Arrange — `sac-control-plane` is on scitex-compute-04 and `spartan-cpu`
    # is on spartan; no single runner carries both. A flattened union would
    # pass this and GitHub would queue it forever.
    repo = _repo_with_workflow(tmp_path, _CROSS_MACHINE)
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert len(found) == 1


# -------- the finding must point at the machine that serves it ------------


def test_rejection_advertises_the_control_plane_destination(
    tmp_path, unrelated_registry
):
    # Arrange — the "Registered destinations:" line is how a reader learns
    # what to target instead. A destination registered but not advertised
    # sends them to write an exemption for a job that had a legal home.
    repo = _repo_with_workflow(tmp_path, _LOOKALIKE)
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert "scitex-compute-04" in found[0].detail


# EOF
