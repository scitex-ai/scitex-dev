"""Unit tests for the RUNNER-DESTINATION surface of scitex_dev.hosts._registry.

Split from `test__registry.py` (that file is at its line budget) — this
module covers only the `runner_labels:` schema added so the registry can
answer "is this CI destination legal?": parsing, `HostRecord.serves`,
`list_runner_destinations`, `find_runner_host`, and the loud failures on a
malformed block.

No mocks (NM001-003) — every case writes a real hosts.yaml under tmp_path
and passes it via the `hosts_path=` seam, so the canonical
`~/.scitex/dev/hosts.yaml` is never read or written. One assert per test
(STX-TQ007 / 02_package/13_test-quality.md), Arrange/Act/Assert.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.hosts import (
    HostRegistryError,
    find_runner_host,
    list_hosts,
    list_runner_destinations,
)

_SPARTAN_TWO_RUNNERS = """\
hosts:
  spartan:
    kind: hpc-login
    ssh_alias: spartan
    scitex_root: "/data/gpfs/projects/punim0264/ywatanabe/.scitex"
    runner_labels:
      - [self-hosted, Linux, X64, spartan-cpu]
      - [self-hosted, Linux, X64, spartan-cpu, scitex-ci]
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
"""

_NO_RUNNERS = """\
hosts:
  nas:
    kind: storage
    ssh_alias: nas
    scitex_root: "~/.scitex"
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "hosts.yaml"
    p.write_text(content)
    return p


# -------- parsing ----------------------------------------------------------


def test_runner_labels_parsed_as_one_set_per_runner(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Assert
    assert len(spartan.runner_labels) == 2


def test_runner_labels_entry_is_a_frozenset_of_labels(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Assert
    assert frozenset({"self-hosted", "Linux", "X64", "spartan-cpu"}) in (
        spartan.runner_labels
    )


def test_host_without_runner_labels_serves_nothing(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    nas = next(h for h in list_hosts(hosts_path=p) if h.name == "nas")
    # Assert
    assert nas.runner_labels == ()


def test_runner_labels_included_in_to_dict(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Assert
    assert sorted(spartan.to_dict()["runner_labels"]) == [
        ["Linux", "X64", "scitex-ci", "self-hosted", "spartan-cpu"],
        ["Linux", "X64", "self-hosted", "spartan-cpu"],
    ]


# -------- malformed blocks fail LOUD ---------------------------------------
#
# Degrading a typo'd registry to "no runners" would turn every workflow in
# the fleet into a PS-224 error for a reason that has nothing to do with the
# workflows — the check would be reporting on data it never actually read.


def test_scalar_runner_labels_block_raises(tmp_path):
    # Arrange
    p = _write(
        tmp_path,
        'hosts:\n  spartan:\n    kind: hpc-login\n    scitex_root: "~/.scitex"\n'
        "    runner_labels: self-hosted\n",
    )

    # Act
    def load_registry():
        return list_hosts(hosts_path=p)

    # Assert
    with pytest.raises(HostRegistryError):
        load_registry()


def test_bare_string_runner_entry_raises(tmp_path):
    # Arrange
    p = _write(
        tmp_path,
        'hosts:\n  spartan:\n    kind: hpc-login\n    scitex_root: "~/.scitex"\n'
        "    runner_labels:\n      - self-hosted\n",
    )

    # Act
    def load_registry():
        return list_hosts(hosts_path=p)

    # Assert
    with pytest.raises(HostRegistryError):
        load_registry()


def test_empty_runner_entry_raises(tmp_path):
    # Arrange
    p = _write(
        tmp_path,
        'hosts:\n  spartan:\n    kind: hpc-login\n    scitex_root: "~/.scitex"\n'
        "    runner_labels:\n      - []\n",
    )

    # Act
    def load_registry():
        return list_hosts(hosts_path=p)

    # Assert
    with pytest.raises(HostRegistryError):
        load_registry()


# -------- HostRecord.serves (GitHub's dispatch rule) -----------------------


def test_serves_exact_label_set(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Act
    served = spartan.serves(["self-hosted", "Linux", "X64", "spartan-cpu"])
    # Assert
    assert served is True


def test_serves_subset_of_a_runners_labels(tmp_path):
    # Arrange — a job may request FEWER labels than the runner carries.
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Act
    served = spartan.serves(["self-hosted", "scitex-ci"])
    # Assert
    assert served is True


def test_does_not_serve_label_no_runner_carries(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Act
    served = spartan.serves(["self-hosted", "scitex-agentic"])
    # Assert
    assert served is False


def test_does_not_serve_labels_split_across_two_runners(tmp_path):
    # Arrange — `sapphire` exists on NEITHER runner; a per-machine flat union
    # would wrongly green-light a combination no single runner offers.
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Act
    served = spartan.serves(["self-hosted", "spartan-cpu", "sapphire"])
    # Assert
    assert served is False


def test_empty_request_is_never_served(tmp_path):
    # Arrange — "no labels at all" names no destination.
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    spartan = next(h for h in list_hosts(hosts_path=p) if h.name == "spartan")
    # Act
    served = spartan.serves([])
    # Assert
    assert served is False


# -------- list_runner_destinations / find_runner_host ----------------------


# These three ask what THIS FILE declares, so they opt out of the packaged
# floor. The floor is unioned in by default (2026-08-15) because a stale local
# registry was reporting live destinations as undeliverable — see
# `test__runner_destination_floor.py`. Reading the file alone is still a real
# question; it is just no longer the default one.


def test_list_runner_destinations_returns_one_pair_per_runner(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    destinations = list_runner_destinations(hosts_path=p, include_packaged_floor=False)
    # Assert
    assert len(destinations) == 2


def test_list_runner_destinations_names_the_owning_host(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    destinations = list_runner_destinations(hosts_path=p, include_packaged_floor=False)
    # Assert
    assert {host for host, _labels in destinations} == {"spartan"}


def test_list_runner_destinations_empty_when_no_machine_hosts_a_runner(tmp_path):
    # Arrange — the REGISTRY-GAP state PS-224 must distinguish from "every
    # workflow is illegal".
    p = _write(tmp_path, _NO_RUNNERS)
    # Act
    destinations = list_runner_destinations(hosts_path=p, include_packaged_floor=False)
    # Assert
    assert destinations == []


def test_find_runner_host_returns_the_serving_machine(tmp_path):
    # Arrange
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    host = find_runner_host(
        ["self-hosted", "Linux", "X64", "scitex-ci"], hosts_path=p
    )
    # Assert
    assert host.name == "spartan"


def test_find_runner_host_returns_none_for_unserved_destination(tmp_path):
    # Arrange — the measured failure: a label set nothing advertises, which
    # GitHub queues forever rather than rejecting.
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    host = find_runner_host(["self-hosted", "scitex-agentic"], hosts_path=p)
    # Assert
    assert host is None


def test_find_runner_host_returns_none_for_hosted_image(tmp_path):
    # Arrange — a GitHub-hosted image is in no machine's runner_labels by
    # construction, so it is unregistered without a special case.
    p = _write(tmp_path, _SPARTAN_TWO_RUNNERS)
    # Act
    host = find_runner_host(["ubuntu-latest"], hosts_path=p)
    # Assert
    assert host is None


# EOF
