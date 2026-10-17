"""Evaluate an explicitly supplied delivery snapshot without taking actions.

This first consumer does not read a Cards store, acquire a controller lease or
send a wake. Its input is an observation prepared through reviewed adapters,
not a guessed store file. Matching supplied identities permits evaluation only;
it does not certify their live provenance. Infra owns that adapter/admission and
timer enrollment. Missing configuration or evidence fails visibly.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO
from uuid import UUID

SCHEMA = "scitex.dev.apps-delivery-observation.v1"
JOB_NAME = "scitex-dev-apps-delivery-observe"
SNAPSHOT_ENV = "SCITEX_DEV_APPS_DELIVERY_SNAPSHOT"
MAX_BYTES = 1_048_576
MAX_CARDS = 64
MAX_PASS_SECONDS = 20
CORE_STAGES = (
    "implementation", "independent_review", "current_CI", "normal_merge",
    "owned_checkout_sync", "artifact_and_runtime_binding",
)
OPTIONAL_STAGES = (
    "service_rollout_if_required", "authenticated_live_acceptance_if_required",
    "public_Visual_CI_demo_if_original_card_requires",
)
_GIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_INSTANCE = re.compile(r"[0-9]+\Z")
_REPO = re.compile(r"scitex-ai/[A-Za-z0-9_.-]+\Z")


class ObservationError(ValueError):
    """A specific observation/controller boundary could not be qualified."""


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ObservationError(code)


def _text(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 512 and value.strip() == value and not any(c in value for c in "\r\n\0")


def _timestamp(value: object) -> datetime:
    _require(_text(value), "missing_observation_time")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ObservationError("invalid_observation_time") from exc
    _require(result.utcoffset() is not None, "timezone_required")
    return result.astimezone(timezone.utc)


def _fresh(value: object, now: datetime, max_age: int) -> bool:
    age = (now - _timestamp(value)).total_seconds()
    return 0 <= age <= max_age


def _uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _matches(pattern: re.Pattern[str], value: object) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _identity(snapshot: dict) -> None:
    identity = snapshot.get("identity")
    _require(isinstance(identity, dict), "missing_identity")
    expected = identity.get("expected_store", {})
    observed = identity.get("observed_store", {})
    _require(isinstance(expected, dict) and isinstance(observed, dict), "missing_store_identity")
    _require(_uuid(expected.get("store_uuid")) and expected["store_uuid"] == observed.get("store_uuid"), "store_identity_mismatch")
    # Cards exposes PostgreSQL system_identifier::text without translating it.
    _require(_matches(_INSTANCE, expected.get("instance_id")) and expected["instance_id"] == observed.get("instance_id"), "store_identity_mismatch")
    _require(observed.get("identity_verdict") == "matches" and observed.get("may_proceed") is True, "store_identity_refused")
    expected = identity.get("expected_controller", {})
    observed = identity.get("observed_controller", {})
    _require(isinstance(expected, dict) and isinstance(observed, dict), "missing_controller_identity")
    for field in ("actor", "controller_id"):
        _require(_text(expected.get(field)) and expected[field] == observed.get(field), "controller_identity_mismatch")
    _require(observed.get("admission") == "snapshot_evaluation_only", "controller_evaluation_not_admitted")
    _require(_text(observed.get("generation")), "missing_controller_generation")


def _required_stages(scope: dict) -> tuple[str, ...]:
    materiality = scope.get("original_scope")
    _require(isinstance(materiality, dict), "missing_original_scope")
    _require(set(materiality) == set(OPTIONAL_STAGES), "incomplete_original_scope")
    _require(all(type(v) is bool for v in materiality.values()), "invalid_original_scope")
    return CORE_STAGES + tuple(stage for stage in OPTIONAL_STAGES if materiality[stage])


def _checkpoint_reason(stage: str, proof: object, scope: dict, now: datetime, max_age: int) -> str | None:
    if not isinstance(proof, dict) or proof.get("status") != "qualified":
        return "checkpoint_not_qualified"
    if (proof.get("source_head_full"), proof.get("source_tree_full")) != (scope["source_head_full"], scope["source_tree_full"]):
        return "stale_source_generation"
    if not all(_text(proof.get(k)) for k in ("evidence_attachment", "actual_read_scope", "actor")):
        return "missing_evidence_readback"
    if not _matches(_SHA256, proof.get("evidence_sha256")):
        return "missing_evidence_identity"
    if proof["actor"] != scope["actors"][stage]:
        return "checkpoint_actor_mismatch"
    if not _fresh(proof.get("last_observed_UTC"), now, max_age):
        return "stale_checkpoint_observation"
    if stage == "independent_review" and proof["actor"] == scope["actors"]["implementation"]:
        return "review_is_not_independent"
    if stage == "current_CI" and proof.get("all_required_current_success") is not True:
        return "required_CI_unqualified"
    if stage == "normal_merge" and not _matches(_GIT, proof.get("merge_head_full")):
        return "missing_actual_merge_identity"
    if stage == "owned_checkout_sync":
        if proof.get("clean") is not True:
            return "checkout_dirty_or_unknown"
        if (proof.get("actual_head_full"), proof.get("actual_tree_full")) != (scope["source_head_full"], scope["source_tree_full"]):
            return "checkout_generation_mismatch"
    if stage in ("artifact_and_runtime_binding",) + OPTIONAL_STAGES:
        if not _matches(_SHA256, proof.get("artifact_hash_full")) or not _text(proof.get("actual_runtime_identity")):
            return "missing_artifact_runtime_binding"
        binding = scope.get("selected_artifact_runtime", {})
        if not isinstance(binding, dict) or (proof["artifact_hash_full"], proof["actual_runtime_identity"]) != (binding.get("artifact_hash_full"), binding.get("actual_runtime_identity")):
            return "artifact_runtime_generation_mismatch"
    return None


def _activity(card: dict) -> dict:
    supplied = card.get("activity", {})
    _require(isinstance(supplied, dict), "invalid_activity_observation")
    result = {"heartbeat": "unknown", "last_handshake_UTC": None, "last_actual_tool_UTC": None}
    for key in ("last_handshake_UTC", "last_actual_tool_UTC"):
        if supplied.get(key) is not None:
            result[key] = _timestamp(supplied[key]).isoformat()
    if supplied.get("heartbeat") in ("live", "stopped", "unknown"):
        result["heartbeat"] = supplied["heartbeat"]
    return result


def _wake_state(card: dict) -> str:
    wake = card.get("wake", {})
    _require(isinstance(wake, dict), "invalid_wake_observation")
    # An HTTP202/send success alone is never a receiver acknowledgement.
    ack = wake.get("receiver_ack")
    if isinstance(ack, dict) and all(_text(ack.get(k)) for k in ("exchange_id", "receiver", "evidence_attachment", "actual_read_scope")):
        _timestamp(ack.get("last_observed_UTC"))
        return "supplied_receiver_ack_observation"
    return "queued_not_acknowledged" if wake.get("http_status") == 202 else "unqualified"


def evaluate_snapshot(snapshot: dict, *, now: datetime | None = None, max_age_seconds: int = 300) -> dict:
    """Return proposed next checkpoints from supplied observations only.

    No returned proposal key is a durable claim or deduplication receipt.
    A successful evaluation means the observation was readable, not delivery
    complete or live store/controller provenance certified.
    """
    started = time.monotonic()
    now = now or datetime.now(timezone.utc)
    _require(now.utcoffset() is not None, "timezone_required")
    _require(type(max_age_seconds) is int and 0 < max_age_seconds <= 300, "invalid_freshness_limit")
    _require(isinstance(snapshot, dict) and snapshot.get("schema") == SCHEMA, "unsupported_snapshot_schema")
    _require(_text(snapshot.get("observation_id")), "missing_observation_id")
    _require(_fresh(snapshot.get("last_observed_UTC"), now, max_age_seconds), "stale_or_future_snapshot")
    _identity(snapshot)
    scopes, cards = snapshot.get("scope"), snapshot.get("cards")
    _require(isinstance(scopes, list) and 0 < len(scopes) <= MAX_CARDS and isinstance(cards, list) and 0 < len(cards) <= MAX_CARDS, "missing_selected_cards")
    _require(all(isinstance(c, dict) and _text(c.get("card_id")) for c in cards + scopes), "invalid_selected_card")
    selected = {c["card_id"]: c for c in scopes}
    observed = {c["card_id"]: c for c in cards}
    _require(len(selected) == len(scopes) and len(observed) == len(cards) and set(selected) == set(observed), "selected_card_census_mismatch")
    findings = []
    for card_id, scope in selected.items():
        _require(time.monotonic() - started < MAX_PASS_SECONDS, "observation_deadline_exceeded")
        _require(_REPO.fullmatch(str(scope.get("source_repo", ""))) is not None, "invalid_source_repo")
        _require(all(_matches(_GIT, scope.get(k)) for k in ("source_head_full", "source_tree_full")), "missing_full_source_identity")
        card = observed[card_id]
        _require(all(card.get(k) == scope[k] for k in ("source_repo", "source_head_full", "source_tree_full")), "current_card_source_mismatch")
        stages = _required_stages(scope)
        actors = scope.get("actors")
        _require(isinstance(actors, dict) and all(_text(actors.get(s)) for s in stages), "missing_next_actor")
        proofs = card.get("checkpoints")
        _require(isinstance(proofs, dict), "missing_checkpoint_observations")
        qualified, next_stage, reason = [], "complete_only_when_original_scope_satisfied", None
        for stage in stages:
            reason = _checkpoint_reason(stage, proofs.get(stage), scope, now, max_age_seconds)
            if reason is not None:
                next_stage = stage
                break
            qualified.append(stage)
        actor = actors[next_stage] if next_stage in stages else None
        evidence = {
            stage: {key: proof.get(key) for key in ("status", "source_head_full", "source_tree_full", "evidence_sha256", "artifact_hash_full", "actual_runtime_identity")}
            for stage, proof in proofs.items() if stage in stages and isinstance(proof, dict)
        }
        generation = {"card_id": card_id, "source_repo": scope["source_repo"], "source_head_full": scope["source_head_full"], "source_tree_full": scope["source_tree_full"], "selected_artifact_runtime": scope.get("selected_artifact_runtime"), "checkpoint_evidence": evidence, "required_stages": stages, "next_stage": next_stage, "next_actor": actor}
        key = hashlib.sha256(json.dumps(generation, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        findings.append({"card_id": card_id, "source_repo": scope["source_repo"], "source_head_full": scope["source_head_full"], "source_tree_full": scope["source_tree_full"], "qualified_supplied_checkpoints": qualified, "next_stage": next_stage, "next_actor": actor, "reason": reason, "proposal_key": key, "activity": _activity(card), "wake_state": _wake_state(card)})
    _require(time.monotonic() - started < MAX_PASS_SECONDS, "observation_deadline_exceeded")
    return {"schema": SCHEMA, "mode": "supplied_snapshot_evaluation_only", "status": "observed", "exit_code": 0, "errors": [], "findings": findings, "live_store_read": False, "live_identity_admission_verified": False, "controller_enrolled": False, "wake_performed": False, "durable_deduplication": False}


def read_snapshot(path: Path) -> dict:
    """Read a finite regular observation input; never discover a store path."""
    _require(path.is_absolute(), "explicit_absolute_snapshot_required")
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        _require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES, "invalid_snapshot_file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_BYTES + 1)
        _require(len(data) <= MAX_BYTES, "snapshot_size_exceeded")
        return json.loads(data)
    finally:
        os.close(fd)


def run_once(*, snapshot_path: Path | None = None, out: TextIO | None = None) -> dict:
    """Emit one read-only result; callers must propagate nonzero exit_code."""
    out = out if out is not None else sys.stdout
    try:
        value = os.environ.get(SNAPSHOT_ENV) if snapshot_path is None else str(snapshot_path)
        _require(_text(value), "missing_snapshot_configuration")
        result = evaluate_snapshot(read_snapshot(Path(value)))
    except (ObservationError, OSError, ValueError, TypeError) as exc:
        # Do not echo input/DSN/environment values or a private-path traceback.
        code = str(exc) if isinstance(exc, ObservationError) else "snapshot_read_or_format_failure"
        result = {"schema": SCHEMA, "mode": "supplied_snapshot_evaluation_only", "status": "controller_failure", "exit_code": 2, "errors": [code], "findings": [], "live_store_read": False, "live_identity_admission_verified": False, "controller_enrolled": False, "wake_performed": False, "durable_deduplication": False}
    out.write(json.dumps(result, sort_keys=True) + "\n")
    return result
