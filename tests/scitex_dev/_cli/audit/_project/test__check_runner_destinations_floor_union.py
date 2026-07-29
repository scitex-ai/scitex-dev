"""PS-224's shipped floor is a UNION with per-host state, never a fallback.

The first implementation read the shipped seed only WHEN the user-state
`hosts.yaml` was empty. That made a central gate's ground truth
subtractable by mutable per-host state: a host that registered even ONE
unrelated machine REPLACED the seed wholesale, hiding `spartan` and turning
every correctly-migrated job red. And because that file is edited live (by
the operator and by agents), the verdict MOVED under repos that changed
nothing — measured 2026-07-29 in scitex-agent-container, where the same
tree passed at 14:56 and failed after a 15:07 edit to `hosts.yaml`.

`test_unrelated_machine_in_user_registry_does_not_hide_the_floor` is the
regression guard: it FAILS on the fallback implementation and passes on the
union. The rest pin the other half of the contract — per-host state still
EXTENDS the floor, a destination NEITHER side serves still ERRORS (without
which the union could be a blanket pass and this suite would not notice),
and an entry in both sides is listed ONCE.

No mocks (NM001-003): every case builds a REAL repo tree under `tmp_path`
plus a REAL `hosts.yaml` passed through the check's `hosts_path=` seam, and
uses the real `floor_destinations=` value seam where a non-default floor is
needed. Nothing is patched.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._violation import Violation

#: A user-state registry naming ONE machine that has nothing to do with the
#: shipped seed's `spartan`. This is the realistic shape: a host registers
#: its own local runner. Under the old FALLBACK it erased the seed.
_REGISTRY_UNRELATED_ONLY = """\
hosts:
  ci-box:
    kind: workstation
    ssh_alias: ci-box
    scitex_root: "~/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, ci-box-local]
"""

#: A user-state registry that DUPLICATES the shipped seed's spartan entries
#: verbatim — the common case, since the on-disk file starts life as a copy
#: of the seed. The union must not list those destinations twice.
_REGISTRY_DUPLICATES_SEED = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, spartan-cpu]
      - [self-hosted, Linux, X64, spartan-cpu, scitex-ci]
"""

#: A destination the SHIPPED seed serves and the user registries above do
#: NOT — so a green verdict here can only come from the floor.
_FLOOR_ONLY = "[self-hosted, Linux, X64, spartan-cpu]"

#: A destination only the USER registry serves — the extend direction.
_USER_ONLY = "[self-hosted, Linux, X64, ci-box-local]"

#: `describe_destinations` sorts labels, so this is the exact rendering of
#: the seed's first spartan runner in the "Registered destinations:" line.
#: The second one carries `scitex-ci` between `X64` and `self-hosted`, so
#: this substring cannot accidentally match it.
_RENDERED_SPARTAN = "spartan: [Linux, X64, self-hosted, spartan-cpu]"


@pytest.fixture
def unrelated_registry(tmp_path) -> Path:
    """A real hosts.yaml registering only a machine the seed never mentions."""
    path = tmp_path / "hosts.yaml"
    path.write_text(_REGISTRY_UNRELATED_ONLY)
    return path


def _repo_with_workflow(tmp_path: Path, body: str) -> Path:
    """Build a repo whose `.github/workflows/ci.yml` holds `body`."""
    repo = tmp_path / "repo"
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "ci.yml").write_text(body)
    return repo


def _workflow(runs_on: str) -> str:
    return f"name: ci\non: [push]\njobs:\n  test:\n    runs-on: {runs_on}\n"


def _run(repo: Path, registry_path: Path) -> list[Violation]:
    out: list[Violation] = []
    check_ps224_runner_destinations(repo, Violation, out, hosts_path=registry_path)
    return out


# -------- REGRESSION: per-host state must not SUBTRACT from the floor ------


def test_unrelated_machine_in_user_registry_does_not_hide_the_floor(
    tmp_path, unrelated_registry
):
    # Arrange — the user registry is NON-EMPTY but knows nothing about
    # spartan. Under the old fallback it replaced the shipped seed and this
    # correctly-migrated job went red for a reason unrelated to the repo.
    repo = _repo_with_workflow(tmp_path, _workflow(_FLOOR_ONLY))
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert found == []


def test_floor_destination_is_listed_even_when_user_state_is_populated(
    tmp_path, unrelated_registry
):
    # Arrange — the error message must advertise the floor too, or a reader
    # is told to target something the gate would then reject.
    repo = _repo_with_workflow(tmp_path, _workflow("[self-hosted, ghost]"))
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert _RENDERED_SPARTAN in found[0].detail


# -------- per-host state still EXTENDS the floor ---------------------------


def test_user_registry_destination_extends_the_floor(tmp_path, unrelated_registry):
    # Arrange — a machine only the LOCAL file knows about is still legal;
    # the union adds to the floor, it does not replace it in either
    # direction.
    repo = _repo_with_workflow(tmp_path, _workflow(_USER_ONLY))
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert found == []


# -------- MUTATION PROOF: the union is not a blanket pass ------------------


def test_destination_served_by_neither_side_still_errors(
    tmp_path, unrelated_registry
):
    # Arrange — `ghost` is in neither the shipped seed nor the user
    # registry. Without this case, a check that unioned everything into an
    # unconditional pass would sail through the two green tests above.
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, ghost]")
    )
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert len(found) == 1


def test_destination_served_by_neither_side_is_severity_error(
    tmp_path, unrelated_registry
):
    # Arrange — E is the whole point: W never affects the exit code.
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, ghost]")
    )
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert found[0].severity == "E"


def test_partial_match_across_the_two_sides_still_errors(
    tmp_path, unrelated_registry
):
    # Arrange — `spartan-cpu` (floor) and `ci-box-local` (user state) are
    # each served, but by DIFFERENT runners. A flattened union would wrongly
    # pass this; GitHub would queue it forever.
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, spartan-cpu, ci-box-local]")
    )
    # Act
    found = _run(repo, unrelated_registry)
    # Assert
    assert len(found) == 1


# -------- dedup: an entry in BOTH sides is listed ONCE ---------------------


def test_destination_in_both_floor_and_user_state_is_listed_once(tmp_path):
    # Arrange — the on-disk file usually starts as a copy of the seed, so
    # every destination would otherwise be printed twice.
    registry_path = tmp_path / "hosts.yaml"
    registry_path.write_text(_REGISTRY_DUPLICATES_SEED)
    repo = _repo_with_workflow(tmp_path, _workflow("[self-hosted, ghost]"))
    # Act
    found = _run(repo, registry_path)
    # Assert
    assert found[0].detail.count(_RENDERED_SPARTAN) == 1


# EOF
