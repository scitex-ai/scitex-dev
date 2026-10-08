"""Organization freshness policy tests (real fakes, no live mutation)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from scitex_dev._ecosystem.freshness_gc import (
    DEFAULT_FRESHNESS_DAYS,
    CardsResult,
    CardsUnavailableError,
    FreshnessPolicy,
    GitHubClient,
    GitHubItem,
    GitHubTransportError,
    cards_cli_available,
    compute_cutoff,
    run_cards_freshness_gc,
    run_freshness_gc,
)

NOW = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=3)


class RecordingTransport:
    """Endpoint-aware in-memory GitHub transport."""

    def __init__(self, responses):
        self.responses = {key: list(value) for key, value in responses.items()}
        self.calls = []

    def request(self, method, endpoint, *, fields=None):
        self.calls.append((method, endpoint, fields))
        key = (method, endpoint)
        values = self.responses.get(key, [])
        if not values:
            raise AssertionError(f"unexpected transport call: {key}")
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _item(number, kind, updated_at, repo="scitex-ai/demo"):
    return GitHubItem(repo=repo, number=number, kind=kind, updated_at=updated_at)


def _run(items, transport, **kwargs):
    client = GitHubClient(transport)
    return run_freshness_gc(
        policy=FreshnessPolicy(),
        now=NOW,
        dry_run=False,
        list_items_fn=lambda organization: list(items),
        github=client,
        cards_mode="off",
        **kwargs,
    )


def _capture_error(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - assertions inspect the real boundary
        return exc
    return None


def test_default_policy_is_three_days():
    # Arrange
    expected = 3
    # Act
    actual = DEFAULT_FRESHNESS_DAYS
    # Assert
    assert actual == expected


def test_compute_cutoff_is_exactly_72_hours_at_default():
    # Arrange
    expected = CUTOFF
    # Act
    actual = compute_cutoff(NOW, DEFAULT_FRESHNESS_DAYS)
    # Assert
    assert actual == expected


def test_exact_72_hour_boundary_is_not_a_candidate():
    # Arrange
    item = _item(1, "issue", CUTOFF)
    # Act
    result = _run([item], RecordingTransport({}))
    # Assert
    assert result.github.candidates == 0


def test_freshened_race_is_rechecked_and_not_closed():
    # Arrange
    endpoint = "/repos/scitex-ai/demo/issues/1"
    transport = RecordingTransport(
        {
            ("GET", endpoint): [
                [{"number": 1, "state": "open", "updated_at": NOW.isoformat()}]
            ]
        }
    )
    stale = _item(1, "issue", CUTOFF - timedelta(seconds=1))
    # Act
    result = _run([stale], transport)
    # Assert
    assert (result.github.closed, result.github.freshened) == (0, 1)


def test_issue_and_pull_request_use_distinct_close_endpoints():
    # Arrange
    issue_endpoint = "/repos/scitex-ai/demo/issues/1"
    pull_endpoint = "/repos/scitex-ai/demo/pulls/2"
    stale_stamp = (CUTOFF - timedelta(seconds=1)).isoformat()
    transport = RecordingTransport(
        {
            ("GET", issue_endpoint): [
                [{"number": 1, "state": "open", "updated_at": stale_stamp}]
            ],
            ("PATCH", issue_endpoint): [[{"state": "closed"}]],
            ("GET", pull_endpoint): [
                [{"number": 2, "state": "open", "updated_at": stale_stamp}]
            ],
            ("PATCH", pull_endpoint): [[{"state": "closed"}]],
        }
    )
    items = [
        _item(1, "issue", CUTOFF - timedelta(seconds=1)),
        _item(2, "pull_request", CUTOFF - timedelta(seconds=1)),
    ]
    # Act
    _run(items, transport)
    patch_endpoints = [
        endpoint for method, endpoint, _ in transport.calls if method == "PATCH"
    ]
    # Assert
    assert patch_endpoints == [issue_endpoint, pull_endpoint]


def test_closing_creates_no_comments_and_only_patches_state():
    # Arrange
    endpoint = "/repos/scitex-ai/demo/issues/1"
    stale_stamp = (CUTOFF - timedelta(seconds=1)).isoformat()
    transport = RecordingTransport(
        {
            ("GET", endpoint): [
                [{"number": 1, "state": "open", "updated_at": stale_stamp}]
            ],
            ("PATCH", endpoint): [[{"state": "closed"}]],
        }
    )
    item = _item(1, "issue", CUTOFF - timedelta(seconds=1))
    # Act
    _run([item], transport)
    clean_calls = all(
        "comments" not in called_endpoint
        and (method != "PATCH" or fields == {"state": "closed"})
        for method, called_endpoint, fields in transport.calls
    )
    # Assert
    assert clean_calls


def test_cards_receives_the_same_exact_cutoff_and_dry_run():
    # Arrange
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return type(
            "Completed",
            (),
            {
                "returncode": 0,
                "stdout": '{"examined": 4, "deleted": 2}',
                "stderr": "",
            },
        )()

    # Act
    result = run_cards_freshness_gc(
        CUTOFF,
        dry_run=True,
        required=True,
        which_fn=lambda name: "/bin/scitex-cards",
        run_fn=run,
    )
    actual = (calls[0][3], "--dry-run" in calls[0], result.counts["deleted"])
    # Assert
    assert actual == ("2026-09-14T12:00:00Z", True, 2)


def test_required_cards_integration_fails_loud_when_unavailable():
    # Arrange
    def invoke():
        return run_cards_freshness_gc(
            CUTOFF,
            dry_run=True,
            required=True,
            which_fn=lambda name: None,
        )

    # Act
    # Assert
    with pytest.raises(CardsUnavailableError):
        invoke()


def test_cards_interface_is_unavailable_when_subcommand_is_missing():
    # Arrange
    def run(argv, **kwargs):
        return type(
            "Completed",
            (),
            {"returncode": 2, "stdout": "", "stderr": "No such command"},
        )()

    # Act
    available = cards_cli_available(
        which_fn=lambda name: "/bin/scitex-cards",
        run_fn=run,
    )
    # Assert
    assert available is False


def test_required_cards_unavailable_aborts_before_github_mutation():
    # Arrange
    transport = RecordingTransport({})

    def invoke():
        return run_freshness_gc(
            policy=FreshnessPolicy(),
            now=NOW,
            dry_run=False,
            list_items_fn=lambda organization: [
                _item(1, "issue", CUTOFF - timedelta(seconds=1))
            ],
            github=GitHubClient(transport),
            cards_mode="required",
            cards_available_fn=lambda: False,
        )

    # Act
    error = _capture_error(invoke)
    actual = (isinstance(error, CardsUnavailableError), transport.calls)
    # Assert
    assert actual == (True, [])


def test_orchestrator_forwards_its_exact_cutoff_to_cards():
    # Arrange
    calls = []

    def cards_fn(cutoff, **kwargs):
        calls.append((cutoff, kwargs))
        return CardsResult(available=True, invoked=True, required=False)

    # Act
    run_freshness_gc(
        policy=FreshnessPolicy(),
        now=NOW,
        dry_run=True,
        list_items_fn=lambda organization: [],
        github=GitHubClient(RecordingTransport({})),
        cards_mode="auto",
        cards_fn=cards_fn,
        cards_available_fn=lambda: True,
    )
    # Assert
    assert calls == [(CUTOFF, {"dry_run": True, "required": False})]


def test_secondary_limit_retries_are_bounded():
    # Arrange
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        if len(calls) < 3:
            return type(
                "Completed",
                (),
                {"returncode": 1, "stdout": "", "stderr": "secondary rate limit"},
            )()
        return type("Completed", (), {"returncode": 0, "stdout": "[]", "stderr": ""})()

    client = GitHubClient.from_gh(
        run_fn=runner, sleep_fn=lambda seconds: None, max_attempts=3
    )
    # Act
    response = client.transport.request("GET", "/orgs/scitex-ai/repos")
    # Assert
    assert response == []


def test_secondary_limit_stops_after_max_attempts():
    # Arrange
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return type(
            "Completed",
            (),
            {"returncode": 1, "stdout": "", "stderr": "secondary rate limit"},
        )()

    client = GitHubClient.from_gh(
        run_fn=runner, sleep_fn=lambda seconds: None, max_attempts=3
    )
    # Act
    error = _capture_error(
        lambda: client.transport.request("GET", "/orgs/scitex-ai/repos")
    )
    actual = (isinstance(error, GitHubTransportError), len(calls))
    # Assert
    assert actual == (True, 3)


def test_result_has_machine_readable_counts():
    # Arrange
    result = _run([], RecordingTransport({}))
    # Act
    payload = result.to_dict()
    encoded = json.dumps(payload)
    actual = (payload["github"]["counts"]["closed"], bool(encoded))
    # Assert
    assert actual == (0, True)
