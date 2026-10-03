"""Pure supplied-observation controls; no Cards, timer or store access."""

from __future__ import annotations

import copy
import errno
import io
import json
from datetime import datetime, timedelta, timezone

import pytest

from scitex_dev._ecosystem_jobs._apps_delivery import (
    CORE_STAGES, OPTIONAL_STAGES, SCHEMA, ObservationError,
    evaluate_snapshot, read_snapshot, run_once,
)

NOW = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)
CARD_HEAD = "1a3815aac3b4162cf3adea29344deea280d3aab8"
CARD_TREE = "267de2fa213fabed83cbc8e2420a991da52ce150"


@pytest.fixture
def snapshot():
    """Synthetic observations carrying actual recorded public source IDs."""
    identity = {"store_uuid": "11111111-1111-4111-8111-111111111111", "instance_id": "7668165447904178049"}
    stages = CORE_STAGES + OPTIONAL_STAGES
    actors = {stage: "scitex-apps-lead" for stage in stages}
    actors["implementation"] = "scitex-cards"
    actors["independent_review"] = "scitex-apps-reviewer"
    scope = {
        "card_id": "cards1057", "source_repo": "scitex-ai/scitex-cards",
        "source_head_full": CARD_HEAD, "source_tree_full": CARD_TREE,
        "original_scope": {stage: True for stage in OPTIONAL_STAGES},
        "actors": actors,
        "selected_artifact_runtime": {"artifact_hash_full": "a" * 64, "actual_runtime_identity": "owned-fixture-generation-1"},
    }
    checkpoints = {}
    for stage in stages:
        checkpoints[stage] = {
            "status": "qualified", "source_head_full": CARD_HEAD,
            "source_tree_full": CARD_TREE, "actor": actors[stage],
            "evidence_attachment": "attachments/synthetic-public-receipt.json",
            "evidence_sha256": "b" * 64,
            "actual_read_scope": "supplied synthetic checkpoint only",
            "last_observed_UTC": NOW.isoformat(),
            "all_required_current_success": True, "merge_head_full": "c" * 40,
            "clean": True, "actual_head_full": CARD_HEAD,
            "actual_tree_full": CARD_TREE, "artifact_hash_full": "a" * 64,
            "actual_runtime_identity": "owned-fixture-generation-1",
        }
    return {
        "schema": SCHEMA, "observation_id": "owned-snapshot-1",
        "last_observed_UTC": NOW.isoformat(),
        "identity": {
            "expected_store": identity,
            "observed_store": dict(identity, identity_verdict="matches", may_proceed=True),
            "expected_controller": {"actor": "scitex-apps-lead", "controller_id": "owned-controller"},
            "observed_controller": {"actor": "scitex-apps-lead", "controller_id": "owned-controller", "admission": "snapshot_evaluation_only", "generation": "source-reviewed-snapshot-1"},
        },
        "scope": [scope],
        "cards": [{"card_id": "cards1057", "source_repo": scope["source_repo"], "source_head_full": CARD_HEAD, "source_tree_full": CARD_TREE, "checkpoints": checkpoints}],
    }


def test_source_complete_cards_keeps_runtime_and_live_scope_open(snapshot):
    # Arrange
    snapshot["cards"][0]["checkpoints"].pop("artifact_and_runtime_binding")
    # Act
    result = evaluate_snapshot(snapshot, now=NOW)
    finding = result["findings"][0]
    # Assert
    assert (finding["next_stage"], finding["qualified_supplied_checkpoints"], result["live_store_read"], result["controller_enrolled"], result["wake_performed"]) == ("artifact_and_runtime_binding", list(CORE_STAGES[:-1]), False, False, False)


def test_writer_standalone_does_not_close_original_service_scope(snapshot):
    # Arrange
    scope, card = snapshot["scope"][0], snapshot["cards"][0]
    scope["card_id"] = card["card_id"] = "writer426"
    scope["source_repo"] = card["source_repo"] = "scitex-ai/scitex-writer"
    scope["source_head_full"] = card["source_head_full"] = "308409a9c6bc4c20600290a6c8a24493922f30a4"
    for proof in card["checkpoints"].values():
        proof["source_head_full"] = scope["source_head_full"]
    card["checkpoints"]["owned_checkout_sync"]["actual_head_full"] = scope["source_head_full"]
    card["checkpoints"]["service_rollout_if_required"]["status"] = "pending"
    # Act
    result = evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert result["findings"][0]["next_stage"] == "service_rollout_if_required"


def test_changed_source_invalidates_old_CI(snapshot):
    # Arrange
    scope, card = snapshot["scope"][0], snapshot["cards"][0]
    scope["source_head_full"] = card["source_head_full"] = "d" * 40
    for stage in CORE_STAGES[:2]:
        card["checkpoints"][stage]["source_head_full"] = scope["source_head_full"]
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert (finding["next_stage"], finding["reason"]) == ("current_CI", "stale_source_generation")


@pytest.mark.parametrize("field,value,reason", [
    ("clean", False, "checkout_dirty_or_unknown"),
    ("clean", None, "checkout_dirty_or_unknown"),
    ("actual_tree_full", "e" * 40, "checkout_generation_mismatch"),
])
def test_dirty_or_wrong_checkout_never_qualifies(snapshot, field, value, reason):
    # Arrange
    snapshot["cards"][0]["checkpoints"]["owned_checkout_sync"][field] = value
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert (finding["next_stage"], finding["reason"]) == ("owned_checkout_sync", reason)


@pytest.mark.parametrize("boundary,field,value,code", [
    ("observed_store", "store_uuid", "33333333-3333-4333-8333-333333333333", "store_identity_mismatch"),
    ("observed_store", "may_proceed", False, "store_identity_refused"),
    ("observed_store", "identity_verdict", "unknown", "store_identity_refused"),
    ("observed_controller", "controller_id", "other-controller", "controller_identity_mismatch"),
    ("observed_controller", "admission", None, "controller_evaluation_not_admitted"),
    ("observed_controller", "generation", None, "missing_controller_generation"),
])
def test_identity_and_admission_gaps_fail(snapshot, boundary, field, value, code):
    # Arrange
    snapshot["identity"][boundary][field] = value
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == code


@pytest.mark.parametrize("stage,field,value,reason", [
    ("independent_review", "actor", "scitex-cards", "checkpoint_actor_mismatch"),
    ("current_CI", "all_required_current_success", False, "required_CI_unqualified"),
    ("normal_merge", "merge_head_full", None, "missing_actual_merge_identity"),
    ("implementation", "evidence_sha256", None, "missing_evidence_identity"),
    ("artifact_and_runtime_binding", "artifact_hash_full", "f" * 64, "artifact_runtime_generation_mismatch"),
    ("artifact_and_runtime_binding", "actual_runtime_identity", None, "missing_artifact_runtime_binding"),
])
def test_checkpoint_counterexamples_remain_open(snapshot, stage, field, value, reason):
    # Arrange
    snapshot["cards"][0]["checkpoints"][stage][field] = value
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert (finding["next_stage"], finding["reason"]) == (stage, reason)


def test_original_scope_cannot_disappear(snapshot):
    # Arrange
    snapshot["scope"][0]["original_scope"].pop(OPTIONAL_STAGES[-1])
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == "incomplete_original_scope"


def test_author_cannot_supply_the_independent_review(snapshot):
    # Arrange
    snapshot["scope"][0]["actors"]["independent_review"] = "scitex-cards"
    snapshot["cards"][0]["checkpoints"]["independent_review"]["actor"] = "scitex-cards"
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert (finding["next_stage"], finding["reason"]) == ("independent_review", "review_is_not_independent")


def test_duplicate_card_rows_refuse_instead_of_last_row_winning(snapshot):
    # Arrange
    snapshot["cards"].append(copy.deepcopy(snapshot["cards"][0]))
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == "selected_card_census_mismatch"


def test_selected_card_missing_is_not_an_empty_board(snapshot):
    # Arrange
    snapshot["cards"] = []
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == "missing_selected_cards"


@pytest.mark.parametrize("seconds", [-1, 301])
def test_expired_and_future_snapshots_fail(snapshot, seconds):
    # Arrange
    snapshot["last_observed_UTC"] = (NOW - timedelta(seconds=seconds)).isoformat()
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == "stale_or_future_snapshot"


def test_unknown_heartbeat_separates_fresh_actual_activity(snapshot):
    # Arrange
    snapshot["cards"][0]["activity"] = {"heartbeat": "unknown", "last_handshake_UTC": None, "last_actual_tool_UTC": NOW.isoformat()}
    # Act
    activity = evaluate_snapshot(snapshot, now=NOW)["findings"][0]["activity"]
    # Assert
    assert activity == {"heartbeat": "unknown", "last_handshake_UTC": None, "last_actual_tool_UTC": NOW.isoformat()}


def test_queued202_is_not_receiver_ACK(snapshot):
    # Arrange
    snapshot["cards"][0]["wake"] = {"http_status": 202, "exchange_id": "queued-only"}
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert finding["wake_state"] == "queued_not_acknowledged"


def test_stable_proposals_do_not_claim_durable_deduplication(snapshot):
    # Arrange
    same, changed = copy.deepcopy(snapshot), copy.deepcopy(snapshot)
    changed["cards"][0]["checkpoints"]["current_CI"]["evidence_sha256"] = "c" * 64
    # Act
    first, second, third = (evaluate_snapshot(s, now=NOW) for s in (snapshot, same, changed))
    keys = [r["findings"][0]["proposal_key"] for r in (first, second, third)]
    # Assert
    assert (keys[0] == keys[1], keys[0] != keys[2], first["durable_deduplication"]) == (True, True, False)


def test_symlink_snapshot_is_refused_without_read(tmp_path):
    # Arrange
    target = tmp_path / "not-a-store.json"
    target.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(target)
    # Act
    with pytest.raises(OSError) as error:
        read_snapshot(link)
    # Assert
    assert error.value.errno == errno.ELOOP


def test_oversize_snapshot_refuses_before_JSON_decode(tmp_path):
    # Arrange
    from scitex_dev._ecosystem_jobs._apps_delivery import MAX_BYTES

    path = tmp_path / "oversize.json"
    path.write_bytes(b"not JSON" + b" " * MAX_BYTES)
    # Act
    with pytest.raises(ObservationError) as error:
        read_snapshot(path)
    # Assert
    assert str(error.value) == "invalid_snapshot_file"


def test_absent_snapshot_reports_controller_failure(tmp_path):
    # Arrange
    out = io.StringIO()
    # Act
    result = run_once(snapshot_path=tmp_path / "absent.json", out=out)
    # Assert
    assert (result["exit_code"], result["errors"], result["findings"], json.loads(out.getvalue())) == (2, ["snapshot_read_or_format_failure"], [], result)


def test_normal_read_once_does_not_certify_live_provenance(snapshot, tmp_path):
    # Arrange
    snapshot["last_observed_UTC"] = datetime.now(timezone.utc).isoformat()
    for proof in snapshot["cards"][0]["checkpoints"].values():
        proof["last_observed_UTC"] = snapshot["last_observed_UTC"]
    path = tmp_path / "explicit-observation.json"
    path.write_text(json.dumps(snapshot))
    out = io.StringIO()
    # Act
    result = run_once(snapshot_path=path, out=out)
    # Assert
    assert (result["exit_code"], result["live_identity_admission_verified"], result["wake_performed"], json.loads(out.getvalue()) == result) == (0, False, False, True)


def test_canonical_decimal_instance_and_matches_verdict_are_preserved(snapshot):
    # Arrange
    expected = snapshot["identity"]["expected_store"]
    observed = snapshot["identity"]["observed_store"]
    # Act
    result = evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert (expected["instance_id"], observed["instance_id"], observed["identity_verdict"], observed["may_proceed"], result["findings"][0]["next_stage"], result["live_identity_admission_verified"]) == ("7668165447904178049", "7668165447904178049", "matches", True, "complete_only_when_original_scope_satisfied", False)


@pytest.mark.parametrize("boundary,field,value,code", [
    ("expected_store", "instance_id", None, "store_identity_mismatch"),
    ("expected_store", "instance_id", "", "store_identity_mismatch"),
    ("expected_store", "instance_id", 7668165447904178049, "store_identity_mismatch"),
    ("expected_store", "instance_id", "22222222-2222-4222-8222-222222222222", "store_identity_mismatch"),
    ("observed_store", "instance_id", "7668165447904178050", "store_identity_mismatch"),
    ("observed_store", "identity_verdict", "differs", "store_identity_refused"),
    ("observed_store", "identity_verdict", "cannot-tell", "store_identity_refused"),
    ("observed_store", "identity_verdict", "ok", "store_identity_refused"),
    ("observed_store", "may_proceed", None, "store_identity_refused"),
    ("observed_store", "may_proceed", 1, "store_identity_refused"),
])
def test_canonical_identity_refusals_remain_explicit(snapshot, boundary, field, value, code):
    # Arrange
    snapshot["identity"][boundary][field] = value
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == code


@pytest.mark.parametrize("field,actual_field", [
    ("source_head_full", "actual_head_full"),
    ("source_tree_full", "actual_tree_full"),
])
def test_numeric_Git_identity_refuses_even_when_all_generations_match(snapshot, field, actual_field):
    # Arrange
    value = int("1" * 40)
    scope, card = snapshot["scope"][0], snapshot["cards"][0]
    scope[field] = card[field] = value
    for proof in card["checkpoints"].values():
        proof[field] = value
    card["checkpoints"]["owned_checkout_sync"][actual_field] = value
    # Act
    with pytest.raises(ObservationError) as error:
        evaluate_snapshot(snapshot, now=NOW)
    # Assert
    assert str(error.value) == "missing_full_source_identity"


@pytest.mark.parametrize("field,actual_field", [
    ("source_head_full", "actual_head_full"),
    ("source_tree_full", "actual_tree_full"),
])
def test_decimal_string_Git_identity_keeps_existing_hex_domain(snapshot, field, actual_field):
    # Arrange
    value = "1" * 40
    scope, card = snapshot["scope"][0], snapshot["cards"][0]
    scope[field] = card[field] = value
    for proof in card["checkpoints"].values():
        proof[field] = value
    card["checkpoints"]["owned_checkout_sync"][actual_field] = value
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert finding["next_stage"] == "complete_only_when_original_scope_satisfied"


@pytest.mark.parametrize("stage,field,value,reason", [
    ("implementation", "evidence_sha256", int("4" * 64), "missing_evidence_identity"),
    ("normal_merge", "merge_head_full", int("3" * 40), "missing_actual_merge_identity"),
    ("artifact_and_runtime_binding", "artifact_hash_full", int("5" * 64), "missing_artifact_runtime_binding"),
])
def test_numeric_checkpoint_identity_refuses_even_when_selected_binding_matches(snapshot, stage, field, value, reason):
    # Arrange
    snapshot["cards"][0]["checkpoints"][stage][field] = value
    snapshot["scope"][0]["selected_artifact_runtime"][field] = value
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert (finding["next_stage"], finding["reason"]) == (stage, reason)


@pytest.mark.parametrize("stage,field,value", [
    ("implementation", "evidence_sha256", "4" * 64),
    ("normal_merge", "merge_head_full", "3" * 40),
    ("artifact_and_runtime_binding", "artifact_hash_full", "5" * 64),
])
def test_decimal_string_checkpoint_identity_keeps_existing_hex_domain(snapshot, stage, field, value):
    # Arrange
    for proof in snapshot["cards"][0]["checkpoints"].values():
        proof[field] = value
    snapshot["scope"][0]["selected_artifact_runtime"][field] = value
    # Act
    finding = evaluate_snapshot(snapshot, now=NOW)["findings"][0]
    # Assert
    assert finding["next_stage"] == "complete_only_when_original_scope_satisfied"
