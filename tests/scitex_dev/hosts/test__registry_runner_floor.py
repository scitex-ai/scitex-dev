#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A STALE local registry must not be able to un-declare a live destination.

Measured on scitex-compute-04, 2026-08-15:

    ~/.scitex/dev/hosts.yaml            written 2026-08-05, records only spartan
    find_runner_host([... "scitex-org-cpu"])   -> None
    packaged_default_runner_destinations()     -> scitex-compute-04 serves it

Four machines were serving `scitex-org-cpu` at that moment — they were the
ONLY runners still online — and this package answered that nothing did.

The audit rule PS-224 was already correct, because it unions the shipped seed
itself. So **one question had two answers depending on which entry point the
caller reached for**, and the narrower one was the default. These tests pin the
union at the entry points every other consumer uses.

`create_default_hosts_yaml` writes the seed ONLY when the file is absent, so
"just re-seed" is not a remedy: a host that has ever had a registry keeps its
stale one forever, silently. That is why the floor is a union at read time
rather than a one-off repair.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scitex_dev.hosts import (
    find_runner_host,
    list_runner_destinations,
    packaged_default_runner_destinations,
)

_ORG_CPU = ["self-hosted", "Linux", "X64", "scitex-org-cpu"]


@pytest.fixture()
def a_registry_knowing_only_one_unrelated_host(tmp_path: Path) -> Path:
    """A user-state registry that is VALID, PARSEABLE, and STALE.

    This is the shape that caused the incident: not a missing file and not a
    corrupt one — either of those fails loud — but a well-formed file whose
    contents stopped describing the fleet.
    """
    path = tmp_path / "hosts.yaml"
    path.write_text(
        "hosts:\n"
        "  ywata-note-win:\n"
        "    kind: workstation\n"
        "    ssh_alias: ywata-note-win\n"
        '    scitex_root: "~/.scitex"\n',
        encoding="utf-8",
    )
    return path


def test_a_stale_registry_still_resolves_a_destination_the_seed_declares(
    a_registry_knowing_only_one_unrelated_host: Path,
) -> None:
    # Arrange
    hosts_path = a_registry_knowing_only_one_unrelated_host
    # Act
    host = find_runner_host(_ORG_CPU, hosts_path=hosts_path)
    # Assert
    assert host is not None, (
        "a local file that is merely OLD must not be able to report a live "
        "destination as undeliverable; the packaged seed is a floor"
    )


def test_opting_out_of_the_floor_answers_the_narrower_file_only_question(
    a_registry_knowing_only_one_unrelated_host: Path,
) -> None:
    """The old behaviour stays reachable, because auditing the FILE is a real
    question — it is just not the question "can this job be picked up"."""
    # Arrange
    hosts_path = a_registry_knowing_only_one_unrelated_host
    # Act
    host = find_runner_host(
        _ORG_CPU, hosts_path=hosts_path, include_packaged_floor=False
    )
    # Assert
    assert host is None


def test_a_label_set_nothing_declares_still_resolves_to_nothing(
    a_registry_knowing_only_one_unrelated_host: Path,
) -> None:
    """The union must not become a blanket pass.

    If widening the source also widened the verdict, the gate would stop being
    a gate — the failure mode this whole change exists to remove.
    """
    # Arrange
    hosts_path = a_registry_knowing_only_one_unrelated_host
    # Act
    host = find_runner_host(["self-hosted", "scitex-agentic"], hosts_path=hosts_path)
    # Assert
    assert host is None


def test_the_destination_list_includes_the_packaged_floor(
    a_registry_knowing_only_one_unrelated_host: Path,
) -> None:
    # Arrange
    hosts_path = a_registry_knowing_only_one_unrelated_host
    # Act
    listed = list_runner_destinations(hosts_path=hosts_path)
    # Assert
    assert set(packaged_default_runner_destinations()) <= set(listed)


def test_the_destination_list_does_not_duplicate_a_pair_both_sources_declare(
    tmp_path: Path,
) -> None:
    """A host that records EXACTLY what the seed records must appear once.

    Otherwise every correctly-maintained registry inflates the destination
    count, and anyone reading capacity off this list is misled in the
    opposite direction from the incident.
    """
    # Arrange
    duplicated = packaged_default_runner_destinations()[0]
    path = tmp_path / "hosts.yaml"
    path.write_text(
        "hosts:\n"
        f"  {duplicated[0]}:\n"
        "    kind: compute\n"
        f"    ssh_alias: {duplicated[0]}\n"
        '    scitex_root: "~/.scitex"\n'
        "    runner_labels:\n"
        f"      - [{', '.join(sorted(duplicated[1]))}]\n",
        encoding="utf-8",
    )
    # Act
    listed = list_runner_destinations(hosts_path=path)
    # Assert
    assert listed.count(duplicated) == 1


@pytest.mark.parametrize(
    "host_name",
    ["scitex-compute-01", "scitex-compute-02", "scitex-compute-03"],
)
def test_the_seed_declares_the_whole_online_compute_pool(host_name: str) -> None:
    """The seed used to carry ONE compute machine and a comment admitting it
    "UNDER-REPORTS the pool by three" — written while that pool was the only
    one still online. Measured 2026-08-15 from `.runner` on each machine plus
    the Actions API, not inferred from the `scitex-0N` naming pattern."""
    # Arrange
    declared = packaged_default_runner_destinations()
    # Act
    serving = [name for name, labels in declared if name == host_name]
    # Assert
    assert serving, f"{host_name} declares no runner destination"


# EOF
