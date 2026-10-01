"""Current measured runner labels pass without relaxing PS-224 or user state."""

from pathlib import Path

import pytest

from scitex_dev._cli.audit._project._check_runner_destinations import (
    check_ps224_runner_destinations,
)
from scitex_dev._cli.audit._project._violation import Violation
from scitex_dev.hosts import (
    create_default_hosts_yaml,
    packaged_default_runner_destinations,
)


def _check(tmp_path: Path, destination: str, registry_text: str = "hosts: {}\n"):
    repo = tmp_path / "repo"
    workflows = repo / ".github/workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: ci\non: push\njobs:\n  test:\n    runs-on: " + destination + "\n"
    )
    registry = tmp_path / "owned-hosts.yaml"
    registry.write_text(registry_text)
    out = []
    check_ps224_runner_destinations(repo, Violation, out, hosts_path=registry)
    return out


@pytest.mark.parametrize("destination", [
    "[self-hosted, Linux, X64, scitex-docker]",
    "[self-hosted, scitex-docker]",
    "scitex-docker",
    "[self-hosted, Linux, X64, scitex-ci, scitex-org-cpu, scitex-local-cpu]",
])
def test_current_primary_destination_passes_the_actual_packaged_floor(tmp_path, destination):
    # Arrange — real workflow and empty owned registry use the shipped floor.
    # Act
    found = _check(tmp_path, destination)
    # Assert
    assert found == []


@pytest.mark.parametrize("destination", [
    "[self-hosted, scitex-ci, scitex-docker]",
    "[self-hosted, scitex-dockers]",
    "[self-hosted, scitex-docker, unregistered-gpu]",
    "${{ vars.ARBITRARY }}",
])
def test_unserved_or_unresolved_destination_still_fails(tmp_path, destination):
    # Arrange — labels from distinct runners cannot be combined into a pool.
    # Act
    found = _check(tmp_path, destination)
    # Assert
    assert [(item.rule, item.where) for item in found] == [
        ("PS-224", ".github/workflows/ci.yml::test")
    ]


def test_current_sets_are_recorded_on_their_measured_hosts():
    # Arrange — authenticated primary inventory measured 2026-10-02.
    cpu = frozenset({"self-hosted", "Linux", "X64", "scitex-ci", "scitex-org-cpu", "scitex-local-cpu"})
    docker = frozenset({"self-hosted", "Linux", "X64", "scitex-docker"})
    expected = [
        ("scitex-compute-02", cpu),
        ("scitex-compute-03", cpu),
        ("scitex-compute-03", docker),
        ("scitex-compute-04", cpu),
    ]
    # Act
    found = [pair for pair in packaged_default_runner_destinations()
             if pair[1] in {cpu, docker}]
    # Assert
    assert found == expected


def test_existing_user_registry_is_not_overwritten(tmp_path):
    # Arrange — a real existing user file must remain byte-identical.
    registry = tmp_path / "owned-hosts.yaml"
    original = "hosts: {}\n# user-owned content\n"
    registry.write_text(original)
    # Act
    create_default_hosts_yaml(registry)
    # Assert
    assert registry.read_text() == original


def test_existing_user_destination_still_extends_the_current_floor(tmp_path):
    # Arrange — the owning file contributes a separately declared runner.
    registry_text = """hosts:
  owned-user-host:
    kind: compute
    ssh_alias: null
    scitex_root: /tmp/owned-user-state
    runner_labels:
      - [self-hosted, owned-user-label]
"""
    # Act
    found = _check(tmp_path, "[self-hosted, owned-user-label]", registry_text)
    # Assert
    assert found == []


def test_populated_user_registry_does_not_hide_current_docker_floor(tmp_path):
    # Arrange — an unrelated nonempty user registry must not replace the floor.
    registry_text = """hosts:
  owned-user-host:
    kind: compute
    ssh_alias: null
    scitex_root: /tmp/owned-user-state
    runner_labels:
      - [self-hosted, owned-user-label]
"""
    # Act
    found = _check(tmp_path, "[self-hosted, Linux, X64, scitex-docker]", registry_text)
    # Assert
    assert found == []
