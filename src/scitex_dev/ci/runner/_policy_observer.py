"""Durable, read-only runner policy observations with a canonical Cards sink.

An uncertain write remains pending. Later ticks reconcile its exact comment
before another delivery; neither a busy runner nor a missing ACK means progress.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import time
import uuid
from pathlib import Path
from typing import Any, Callable

CONTRACT = "dev.ci-runner-policy-observer/v1"
STORE_UUID = "1d55dd6e-3d2a-4c24-a429-a78835ab988f"
STORE_INSTANCE = "7672112238472680366"
ASSIGNEE = "scitex-infrastructure-lead"
TASK_ID = "ci-runner-policy-scitex-ai-20261003"
REMINDER_SECONDS = 3600


class PolicyObserverError(RuntimeError):
    """The observer cannot prove its state or canonical delivery target."""


def _private_file(path: Path, *, create: bool = False) -> int:
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(path, flags | (os.O_CREAT if create else 0), 0o600)
    metadata = os.fstat(fd)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        os.close(fd)
        raise PolicyObserverError("observer file is not owned private regular data")
    return fd


def _read_state(path: Path) -> dict:
    try:
        fd = _private_file(path)
    except FileNotFoundError:
        return {"schema": 1}
    with os.fdopen(fd, "r") as stream:
        state = json.load(stream)
    if not isinstance(state, dict) or state.get("schema") != 1:
        raise PolicyObserverError("observer state is malformed")
    return state


def _save_state(path: Path, state: dict) -> None:
    temporary = path.with_name(".state-" + uuid.uuid4().hex)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise PolicyObserverError("observer state directory ownership drift")
        fd = os.open(
            temporary.name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory,
        )
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(state, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(
                temporary.name, path.name, src_dir_fd=directory, dst_dir_fd=directory
            )
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary.name, dir_fd=directory)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory)


def _condition(report: dict) -> str:
    selected = {
        key: report.get(key)
        for key in (
            "state",
            "violations",
            "unknown",
            "groups",
            "workflow_source",
            "organization",
        )
    }
    return hashlib.sha256(
        json.dumps(_stable_condition(selected), sort_keys=True).encode()
    ).hexdigest()


def _stable_condition(value):
    if isinstance(value, dict):
        return {key: _stable_condition(item) for key, item in value.items()}
    if isinstance(value, list):
        return sorted(
            (_stable_condition(item) for item in value),
            key=lambda item: json.dumps(item, sort_keys=True),
        )
    return value


def _qualify_store(api) -> dict:
    target = api.resolve_store()
    if (
        target.get("may_proceed") is not True
        or target.get("store_uuid") != STORE_UUID
        or str(target.get("instance_id")) != STORE_INSTANCE
        or target.get("expected_uuid") != STORE_UUID
        or str(target.get("expected_instance")) != STORE_INSTANCE
    ):
        raise PolicyObserverError("canonical Cards UUID/instance admission refused")
    return {"store_uuid": STORE_UUID, "instance_id": STORE_INSTANCE}


def _card(api) -> dict | None:
    try:
        card = api.get_task(task_id=TASK_ID)
    except api.TaskNotFoundError:
        return None
    if (
        card.get("id") != TASK_ID
        or card.get("assignee") != ASSIGNEE
        or card.get("agent") != ASSIGNEE
        or card.get("status") in {"done", "cancelled", "completed"}
    ):
        raise PolicyObserverError("policy observer Card owner/status drift")
    return card


def _confirmed(card: dict | None, pending: dict) -> str | None:
    matches = [
        entry
        for entry in (card or {}).get("comments", [])
        if isinstance(entry, dict)
        and entry.get("author") == ASSIGNEE
        and entry.get("text") == pending["text"]
        and isinstance(entry.get("id"), str)
        and entry["id"]
    ]
    if len(matches) > 1:
        raise PolicyObserverError("duplicate policy delivery needs review")
    return matches[0]["id"] if matches else None


def _accept(state: dict, pending: dict, comment_id: str, now: float) -> None:
    state.update(
        last_digest=pending["digest"],
        last_state=pending["state"],
        last_delivery_at=now,
        last_comment_id=comment_id,
    )
    state.pop("pending", None)


def _delivery_text(report: dict, kind: str, digest: str, token: str) -> str:
    activity = report.get("activity") or {}
    lines = [
        f"Runner policy {kind}: {report['state']}",
        f"Observed: {report.get('observed_at', 'unknown')}",
        f"Condition: {digest}",
        f"Delivery: {token}",
    ]
    lines += ["Policy: " + value for value in report.get("violations", [])]
    lines += ["Unknown: " + value for value in report.get("unknown", [])]
    lines += [
        "Last completed job (bounded Dev sample): "
        + str(activity.get("last_completed_job_at") or "unknown"),
        "Sample complete: " + str(activity.get("sample_complete")),
        "Busy is registration activity, not proof of productive work.",
    ]
    return "\n".join(lines)


def _deliver(api, pending: dict) -> str:
    _qualify_store(api)
    card = _card(api)
    if card is None:
        _qualify_store(api)
        api.add_task(
            id=TASK_ID,
            title="Organization runner policy observations",
            status="in_progress",
            assignee=ASSIGNEE,
            created_by=ASSIGNEE,
            project="scitex-dev",
            kind="task",
            note="Operator2248: organization members only; external/fork/UNKNOWN hosted. Read-only observer; no runner/group/workflow mutation.",
        )
        card = _card(api)
    _qualify_store(api)
    api.comment_task(
        task_id=TASK_ID, text=pending["text"], by=ASSIGNEE, kind="ci-runner-policy"
    )
    comment_id = _confirmed(_card(api), pending)
    if comment_id is None:
        raise PolicyObserverError("delivery has no exact Card readback")
    return comment_id


def _default_cards_api():
    try:
        from scitex_cards import _store
    except ImportError as error:
        raise PolicyObserverError(
            "Cards package unavailable; no durable policy alert"
        ) from error

    return _store


def _observe_locked(report: dict, path: Path, api, now: float) -> dict:
    state = _read_state(path)
    digest = _condition(report)
    target = _qualify_store(api)
    pending = state.get("pending")
    if pending is not None:
        comment_id = _confirmed(_card(api), pending)
        if comment_id is None:
            return {"delivery": "unknown-pending", "exit_code": 1, **target}
        _accept(state, pending, comment_id, now)
        _save_state(path, state)
    recovering = report["state"] == "conformant" and state.get("last_state") not in (
        None,
        "conformant",
    )
    changed = state.get("last_digest") != digest
    reminder = now - state.get("last_delivery_at", now) >= REMINDER_SECONDS
    if report["state"] == "conformant" and not recovering:
        return {"delivery": "no-alert-needed", "exit_code": 0, **target}
    if not (changed or reminder or recovering):
        return {"delivery": "deduplicated", "exit_code": 1, **target}
    kind = "recovery" if recovering else "alert" if changed else "reminder"
    pending = {
        "digest": digest,
        "state": report["state"],
        "created_at": now,
        "text": _delivery_text(report, kind, digest, uuid.uuid4().hex),
    }
    state["pending"] = pending
    _save_state(path, state)
    comment_id = _deliver(api, pending)
    _accept(state, pending, comment_id, now)
    _save_state(path, state)
    return {
        "delivery": kind + "-confirmed",
        "comment_id": comment_id,
        "exit_code": 0 if recovering else 1,
        **target,
    }


def observe_once(
    *,
    dry_run: bool = False,
    state_dir: Path | None = None,
    collector: Callable[[], dict] | None = None,
    cards_api: Any = None,
    clock: Callable[[], float] = time.time,
) -> dict:
    """One bounded policy pass; writes only owned state and admitted Cards."""
    from ._policy import collect_policy

    report = (collector or collect_policy)()
    result = {
        **report,
        "contract": CONTRACT,
        "observer_source_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "report": report,
    }
    if report.get("state") not in {"conformant", "violation", "unknown"}:
        raise PolicyObserverError("policy producer returned an unknown state")
    if dry_run:
        return {
            **result,
            "delivery": "dry-run-no-write",
            "exit_code": 0 if report["state"] == "conformant" else 1,
        }
    root = state_dir or Path.home() / ".scitex/dev/runtime/ci-runner-policy"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata = root.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise PolicyObserverError("observer directory is not owned private state")
    fd = _private_file(root / "observer.lock", create=True)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {**result, "delivery": "overlap-held", "exit_code": 1}
        try:
            api = cards_api if cards_api is not None else _default_cards_api()
            delivery = _observe_locked(report, root / "state.json", api, clock())
        except Exception as error:  # noqa: BLE001 -- preserve pending, report nonzero; never expose credential-bearing API exception text.
            delivery = {
                "delivery": "refused-or-unknown",
                "exit_code": 1,
                "exception_type": type(error).__name__,
            }
            if isinstance(error, PolicyObserverError):
                delivery["refusal_reason"] = str(error)
        return {**result, **delivery}
    finally:
        os.close(fd)
