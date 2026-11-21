"""Workflow lifecycle facts cannot disappear behind a partial green check list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scitex_dev.ci._mergeable import _decide, _to_checks
from scitex_dev.ci._readiness import Readiness
from scitex_dev.ci._workflow_waits import apply_workflow_waits

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/workflow-pending-before-jobs.json").read_text()
)
HEAD = FIXTURE["head"]


def _check_verdict():
    # CLEAN models a branch without another protection blocking the merge.
    return _decide(
        "scitex-ai/scitex-db#103",
        HEAD,
        _to_checks(FIXTURE["checks"], HEAD),
        {"mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
    )


def test_observed_pending_workflow_blocks_partial_green_checks():
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, FIXTURE["workflow_pages"])
    # Assert
    assert result.readiness is Readiness.NOT_READY


def test_observed_pending_workflow_emits_no_merge_command():
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, FIXTURE["workflow_pages"])
    # Assert
    assert result.merge_command is None


def test_pending_reason_names_actual_workflow_state():
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, FIXTURE["workflow_pages"])
    # Assert
    assert any("workflow ci: PENDING" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    "status", ["queued", "in_progress", "waiting", "requested", "action_required"]
)
def test_other_unfinished_workflow_states_block(status):
    # Arrange
    pages = [{"workflow_runs": [{"head_sha": HEAD, "name": "ci", "status": status}]}]
    # Act
    result = apply_workflow_waits(_check_verdict(), pages)
    # Assert
    assert result.readiness is Readiness.NOT_READY


@pytest.mark.parametrize(
    "pages",
    [
        None,
        [],
        [{}],
        [{"workflow_runs": None}],
        [{"workflow_runs": [None]}],
        [{"workflow_runs": [{"head_sha": "other", "status": "completed"}]}],
    ],
)
def test_missing_or_malformed_queue_evidence_is_unknown(pages):
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, pages)
    # Assert
    assert result.readiness is Readiness.CANNOT_DETERMINE


def test_api_failure_does_not_promote_partial_checks_to_ready():
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, None, "API unavailable")
    # Assert
    assert result.readiness is Readiness.CANNOT_DETERMINE


@pytest.mark.parametrize(
    "pages",
    [
        [{"workflow_runs": []}],
        [
            {
                "workflow_runs": [
                    {
                        "head_sha": HEAD,
                        "name": "ci",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ]
            }
        ],
    ],
)
def test_no_unfinished_workflows_preserves_existing_verdict(pages):
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, pages)
    # Assert
    assert result == verdict


def test_existing_branch_block_survives_workflow_api_failure():
    # Arrange
    verdict = _decide(
        "scitex-ai/scitex-db#103",
        HEAD,
        _to_checks(FIXTURE["checks"], HEAD),
        {"mergeable": "MERGEABLE", "mergeStateStatus": "BLOCKED"},
    )
    # Act
    result = apply_workflow_waits(verdict, None, "API unavailable")
    # Assert
    assert result.readiness is Readiness.NOT_READY


def test_workflow_wait_does_not_create_check_rows():
    # Arrange
    verdict = _check_verdict()
    # Act
    result = apply_workflow_waits(verdict, FIXTURE["workflow_pages"])
    # Assert
    assert result.checks == verdict.checks


def test_pending_workflow_on_later_page_is_not_ignored():
    # Arrange
    pages = [{"workflow_runs": []}] + FIXTURE["workflow_pages"]
    # Act
    result = apply_workflow_waits(_check_verdict(), pages)
    # Assert
    assert result.readiness is Readiness.NOT_READY


def test_unknown_workflow_status_is_not_ready_evidence():
    # Arrange
    pages = [
        {"workflow_runs": [{"head_sha": HEAD, "name": "ci", "status": "future-state"}]}
    ]
    # Act
    result = apply_workflow_waits(_check_verdict(), pages)
    # Assert
    assert result.readiness is Readiness.CANNOT_DETERMINE
