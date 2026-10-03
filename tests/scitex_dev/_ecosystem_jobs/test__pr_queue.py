"""Actual retained GitHub history and conservative retirement boundaries."""

import json
import os
from copy import deepcopy
from pathlib import Path

import pytest

from scitex_dev._ecosystem_jobs import _pr_queue
from scitex_dev._ecosystem_jobs._pr_queue import cancellation_candidate, next_page


def observed():
    return json.loads(
        Path(__file__).with_name("pr_queue_actual_20261003.json").read_text()
    )


def test_ineligible_oldest_page_cannot_starve_the_next_pages():
    # Arrange: actual observed personal dotfiles queue contained67 runs.
    cursor = None
    pages = []

    # Act
    for _ in range(5):
        page, cursor = next_page(cursor, 67)
        pages.append(page)

    # Assert
    assert pages == [4, 3, 2, 1, 4]


def test_shrinking_queue_clamps_the_saved_cursor():
    # Arrange
    saved, current_count = 4, 3

    # Act
    page, following = next_page(saved, current_count)

    # Assert
    assert (page, following) == (1, 1)


def test_actual_superseded_queue_with_completed_failure_is_admitted():
    # Arrange: real GitHub evidence retained before normal cancellation.
    evidence = observed()

    # Act
    admitted = cancellation_candidate(
        evidence["run"], evidence["pull"], evidence["jobs"]
    )

    # Assert
    assert admitted


def test_candidate_decision_preserves_completed_failure_history():
    # Arrange
    evidence = observed()
    before = deepcopy(evidence["jobs"])

    # Act
    cancellation_candidate(evidence["run"], evidence["pull"], evidence["jobs"])

    # Assert
    assert evidence["jobs"] == before


def _refusal_cases():
    evidence = observed()
    return [
        ("pull", ("head", "sha"), evidence["run"]["head_sha"]),
        ("jobs", ("jobs", 1, "status"), "in_progress"),
        ("pull", ("state",), "closed"),
        ("jobs", ("jobs", 1, "status"), "unmeasured"),
        ("jobs", ("total_count",), evidence["jobs"]["total_count"] + 1),
        ("run", ("event",), "push"),
        (
            "run",
            ("pull_requests",),
            evidence["run"]["pull_requests"] + [{"number": 999}],
        ),
    ]


@pytest.mark.parametrize("target,path,value", _refusal_cases())
def test_current_running_unknown_and_unbound_observations_refuse(target, path, value):
    # Arrange: change one admission boundary of the retained actual observation.
    evidence = observed()
    node = evidence[target]
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value

    # Act
    admitted = cancellation_candidate(
        evidence["run"], evidence["pull"], evidence["jobs"]
    )

    # Assert
    assert not admitted


def test_same_real_lock_identity_is_admitted(tmp_path):
    # Arrange
    lock = tmp_path / "owner.lock"
    lock.write_bytes(b"")
    before = lock.stat()

    # Act
    result = _pr_queue._same_lock(lock, (before.st_dev, before.st_ino))

    # Assert
    assert result is None


def test_replaced_real_lock_refuses_while_original_descriptor_is_held(tmp_path):
    # Arrange: two genuine file inodes, retaining the first descriptor.
    lock = tmp_path / "owner.lock"
    lock.write_bytes(b"")
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"")

    # Act
    with lock.open("rb") as held:
        before = os.fstat(held.fileno())
        replacement.replace(lock)

        # Assert
        with pytest.raises(ValueError, match="Owning job lock was replaced"):
            _pr_queue._same_lock(lock, (before.st_dev, before.st_ino))
