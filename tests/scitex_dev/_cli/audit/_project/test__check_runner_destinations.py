"""Unit tests for PS-224 — runner destination must exist in the machine registry.

No mocks (NM001-003): every case builds a REAL repo tree under `tmp_path`
(`.github/workflows/*.yml`) plus a REAL `hosts.yaml`, and passes the latter
through the check's `hosts_path=` file-path seam. Nothing is patched, and
the canonical `~/.scitex/dev/hosts.yaml` is never read.

One assert per test (STX-TQ007), Arrange/Act/Assert markers (STX-TQ002).

`.github` is a HIDDEN directory — the fixtures build that path explicitly
rather than relying on any walker, because a walker that skips dotted dirs
returns zero findings, which is indistinguishable from "the check passed".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._violation import Violation

_REGISTRY = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, spartan-cpu]
      - [self-hosted, Linux, X64, spartan-cpu, scitex-ci]
"""

_REGISTRY_NO_RUNNERS = """\
hosts:
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
"""

_FLEET_IDIOM = (
    "${{ fromJSON(vars.CI_RUNS_ON || "
    "'[\"self-hosted\",\"Linux\",\"X64\",\"scitex-ci\"]') }}"
)


@pytest.fixture
def registry(tmp_path) -> Path:
    """A real hosts.yaml recording spartan's two live runner label sets."""
    path = tmp_path / "hosts.yaml"
    path.write_text(_REGISTRY)
    return path


def _repo_with_workflow(tmp_path: Path, body: str, name: str = "ci.yml") -> Path:
    """Build a repo whose `.github/workflows/<name>` holds `body`."""
    repo = tmp_path / "repo"
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / name).write_text(body)
    return repo


def _workflow(runs_on: str, job_id: str = "test") -> str:
    return f"name: ci\non: [push]\njobs:\n  {job_id}:\n    runs-on: {runs_on}\n"


def _run(
    repo: Path,
    registry_path: Path,
    *,
    floor: list | None = None,
) -> list[Violation]:
    out: list[Violation] = []
    check_ps224_runner_destinations(
        repo, Violation, out, hosts_path=registry_path, floor_destinations=floor
    )
    return out


# -------- registered destinations pass -------------------------------------


def test_registered_list_destination_is_clean(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, spartan-cpu]")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_fleet_fromjson_idiom_is_clean(tmp_path, registry):
    # Arrange — the literal fallback inside the expression is what runs
    # whenever the CI_RUNS_ON variable is unset, so it is the real
    # destination and is what gets validated.
    repo = _repo_with_workflow(tmp_path, _workflow(_FLEET_IDIOM))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_subset_of_a_runners_labels_is_clean(tmp_path, registry):
    # Arrange — a job may request fewer labels than the runner carries.
    repo = _repo_with_workflow(tmp_path, _workflow("[self-hosted, scitex-ci]"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_labels_mapping_form_is_clean(tmp_path, registry):
    # Arrange — GitHub's `runs-on: {labels: [...]}` spelling.
    repo = _repo_with_workflow(
        tmp_path, _workflow("{labels: [self-hosted, Linux, X64, scitex-ci]}")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_repo_without_workflows_is_clean(tmp_path, registry):
    # Arrange
    repo = tmp_path / "repo"
    repo.mkdir()
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_uses_job_without_runs_on_is_not_flagged(tmp_path, registry):
    # Arrange — a `uses:` job delegates its destination to the reusable
    # workflow's own file; this rule's known static boundary.
    repo = _repo_with_workflow(
        tmp_path,
        "name: ci\non: [push]\njobs:\n  call:\n    uses: scitex-ai/.github/"
        ".github/workflows/shared.yml@main\n",
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


# -------- POSITIVE CONTROL: a destination no machine serves ----------------


def test_nonexistent_machine_label_is_flagged(tmp_path, registry):
    # Arrange — `scitex-agentic` is in no machine's runner_labels.
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, scitex-agentic]")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_nonexistent_machine_finding_is_severity_error(tmp_path, registry):
    # Arrange — E is the whole point: W never affects the exit code.
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, scitex-agentic]")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert found[0].severity == "E"


def test_nonexistent_machine_finding_carries_the_rule_code(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, scitex-agentic]")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert found[0].rule == "PS-224"


def test_nonexistent_machine_finding_names_the_job(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(
        tmp_path,
        _workflow("[self-hosted, Linux, X64, scitex-agentic]", job_id="publish"),
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert "publish" in found[0].detail


def test_github_hosted_image_is_accepted(tmp_path, registry):
    # Arrange — INVERTED 2026-08-02. This test previously asserted that a
    # hosted image IS flagged, on the reasoning that it appears in no
    # machine's runner_labels "by construction, so it needs no special case".
    # That reasoning was sound until constitution §4 made GitHub-hosted the
    # DEFAULT for public repos; the rule then errored on every compliant
    # workflow. GitHub serves these on demand, always, so they cannot produce
    # the unmatchable job PS-224 exists to report.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found == []


def test_a_typo_of_a_hosted_image_is_still_flagged(tmp_path, registry):
    # Arrange — the acceptance is a LITERAL set, never a `ubuntu-*` prefix
    # match. A near-miss is exactly the unservable destination this rule is
    # for, and a fuzzy match would forgive it.
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latests"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_a_hosted_image_combined_with_other_labels_is_still_flagged(
    tmp_path, registry
):
    # Arrange — `[ubuntu-latest, self-hosted]` matches NO runner: not the
    # hosted pool (which serves the bare label) and no machine of ours. The
    # acceptance requires the hosted label to be the WHOLE destination.
    repo = _repo_with_workflow(
        tmp_path, _workflow(["ubuntu-latest", "self-hosted"])
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_labels_split_across_two_runners_is_flagged(tmp_path, registry):
    # Arrange — `sapphire` is on neither runner; a flat per-machine union
    # would wrongly pass this.
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, spartan-cpu, sapphire]")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_fromjson_literal_naming_unserved_labels_is_flagged(tmp_path, registry):
    # Arrange — the expression form must be validated on its literal
    # fallback, not waved through for being an expression.
    repo = _repo_with_workflow(
        tmp_path,
        _workflow(
            "${{ fromJSON(vars.CI_RUNS_ON || '[\"self-hosted\",\"ghost\"]') }}"
        ),
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_every_unserved_job_in_a_file_is_flagged(tmp_path, registry):
    # Arrange — two bad jobs must yield two findings, not one per file.
    # Job `a` used `ubuntu-latest` until 2026-08-02, when hosted images became
    # ACCEPTED and this silently became a one-bad-job fixture testing nothing
    # about per-job counting. A fictional label cannot be rehabilitated by a
    # future policy the way a real platform image was.
    repo = _repo_with_workflow(
        tmp_path,
        "name: ci\non: [push]\njobs:\n"
        "  a:\n    runs-on: moon-base-alpha\n"
        "  b:\n    runs-on: [self-hosted, ghost]\n",
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 2


def test_yaml_workflow_extension_is_scanned(tmp_path, registry):
    # Arrange — both `.yml` and `.yaml` are real in this fleet. The subject
    # here is the EXTENSION, so the destination just has to be one that fires.
    repo = _repo_with_workflow(
        tmp_path, _workflow("moon-base-alpha"), name="release.yaml"
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


# -------- unresolvable destinations are violations too ---------------------
#
# Deliberately different from PS-169, which leaves unresolvable runners
# alone. The mandate here is that every workflow NAMES its destination; a
# destination that cannot be read statically names none, and without this
# case wrapping any label in a variable is a universal bypass.


def test_bare_variable_expression_is_flagged(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(tmp_path, _workflow("${{ vars.RUNNER }}"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_matrix_expression_is_flagged(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(tmp_path, _workflow("${{ matrix.os }}"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_fromjson_without_literal_fallback_is_flagged(tmp_path, registry):
    # Arrange — nothing static to read inside the expression.
    repo = _repo_with_workflow(
        tmp_path, _workflow("${{ fromJSON(vars.CI_RUNS_ON) }}")
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


def test_unresolvable_destination_is_severity_error(tmp_path, registry):
    # Arrange
    repo = _repo_with_workflow(tmp_path, _workflow("${{ vars.RUNNER }}"))
    # Act
    found = _run(repo, registry)
    # Assert
    assert found[0].severity == "E"


# -------- a check that could not run must not report a pass ----------------


def test_unparseable_workflow_is_flagged(tmp_path, registry):
    # Arrange — invalid YAML: its destinations cannot be verified at all.
    repo = _repo_with_workflow(
        tmp_path, "name: ci\njobs:\n  test:\n   runs-on: [unclosed\n"
    )
    # Act
    found = _run(repo, registry)
    # Assert
    assert len(found) == 1


# -------- FLOOR: the shipped seed backs an empty user registry -------------
#
# scitex-dev owns the single registry and ships the canonical seed IN its
# own code. When a host's user-state `hosts.yaml` contributes no runner
# destinations (absent, or a stale pre-`runner_labels` copy that
# `create_default_hosts_yaml` won't refresh), the rule falls back to that
# shipped seed rather than reporting a gap — a stale/empty local file must
# not be able to turn every workflow red for a reason unrelated to the
# workflows. It is NOT a softening: genuine mismatches still error, and if
# even the seed carried no destinations the gap finding would return
# (proved by the mutation test below).


def test_empty_user_registry_falls_back_to_shipped_seed_floor(tmp_path):
    # Arrange — user registry records a host but no runners; the fleet
    # idiom's destination is served by the SHIPPED seed's spartan runner.
    registry_path = tmp_path / "hosts.yaml"
    registry_path.write_text(_REGISTRY_NO_RUNNERS)
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, scitex-ci]")
    )
    # Act
    found = _run(repo, registry_path)
    # Assert
    assert found == []


def test_floor_still_flags_an_unserved_destination(tmp_path):
    # Arrange — with the floor active, a destination the seed does not
    # serve is STILL a violation: the floor is real data, not a blanket pass.
    registry_path = tmp_path / "hosts.yaml"
    registry_path.write_text(_REGISTRY_NO_RUNNERS)
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, sapphire]")
    )
    # Act
    found = _run(repo, registry_path)
    # Assert
    assert len(found) == 1


def test_floor_unserved_finding_is_severity_error(tmp_path):
    # Arrange
    registry_path = tmp_path / "hosts.yaml"
    registry_path.write_text(_REGISTRY_NO_RUNNERS)
    repo = _repo_with_workflow(
        tmp_path, _workflow("[self-hosted, Linux, X64, sapphire]")
    )
    # Act
    found = _run(repo, registry_path)
    # Assert
    assert found[0].severity == "E"


# -------- MUTATION PROOF: the floor is load-bearing ------------------------
#
# Neutralise the shipped seed by injecting an EMPTY floor through the check's
# real `floor_destinations=` value seam (no mock — the same no-patch
# philosophy as `hosts_path`). The empty-user registry then has nothing to
# fall back to, and the honest "could not check" gap finding must return. If
# these go green with `floor=[]` while the floor tests above go green with
# the default floor, the floor is genuinely what makes those pass.


def test_gap_finding_returns_when_even_the_seed_is_empty(tmp_path):
    # Arrange — user registry empty AND floor neutralised: a real gap.
    registry_path = tmp_path / "hosts.yaml"
    registry_path.write_text(_REGISTRY_NO_RUNNERS)
    repo = _repo_with_workflow(
        tmp_path,
        "name: ci\non: [push]\njobs:\n"
        "  a:\n    runs-on: ubuntu-latest\n"
        "  b:\n    runs-on: [self-hosted, ghost]\n",
    )
    # Act — two bad jobs must still yield exactly ONE gap finding.
    found = _run(repo, registry_path, floor=[])
    # Assert
    assert len(found) == 1


def test_gap_finding_names_the_registry_file_when_seed_empty(tmp_path):
    # Arrange
    registry_path = tmp_path / "hosts.yaml"
    registry_path.write_text(_REGISTRY_NO_RUNNERS)
    repo = _repo_with_workflow(tmp_path, _workflow("ubuntu-latest"))
    # Act
    found = _run(repo, registry_path, floor=[])
    # Assert
    assert found[0].where == str(registry_path)


# NOTE: the `audit.exemptions` cases (job-qualified site key, the same-file
# other-job over-exemption guard, reason-mandatory) live in the sibling
# `test__check_runner_destinations_exemptions.py` — this file is at its
# 512-line budget.


# EOF
