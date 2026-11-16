"""Account for unfinished Actions workflows before their check jobs exist."""

from __future__ import annotations

from dataclasses import replace

from ._check_run import PENDING_STATES
from ._readiness import MergeReadiness, Readiness


def apply_workflow_waits(
    verdict: MergeReadiness,
    pages: object,
    error: str | None = None,
) -> MergeReadiness:
    """Add workflow-level waiting facts without weakening check-level gates.

    Pages are the real Actions runs API response from gh --paginate --slurp.
    Completed workflow outcomes remain subject to the existing per-check
    decision. This is not discovery of every expected or required workflow.
    Missing/malformed evidence cannot promote a verdict to READY.
    """
    waits: list[str] = []
    unknown: list[str] = []
    if error:
        unknown.append(f"cannot inspect workflow queue: {error}")
    elif not isinstance(pages, list) or not pages:
        unknown.append("workflow queue response has no page list")
    else:
        for page in pages:
            if not isinstance(page, dict) or not isinstance(
                page.get("workflow_runs"), list
            ):
                unknown.append("workflow queue response has no workflow_runs list")
                continue
            for run in page["workflow_runs"]:
                if not isinstance(run, dict) or run.get("head_sha") != verdict.head_sha:
                    unknown.append("workflow queue row does not identify this head")
                    continue
                state = str(run.get("status") or "").upper()
                name = str(run.get("name") or "<unnamed>")
                if state in PENDING_STATES:
                    waits.append(
                        f"workflow {name}: {state} on this head; its check jobs "
                        "may not exist yet (not a completed CI verdict)"
                    )
                elif state != "COMPLETED":
                    unknown.append(f"workflow {name} has an unknown lifecycle status")
    if not waits and not unknown:
        return verdict
    state = (
        Readiness.NOT_READY
        if waits or verdict.readiness is Readiness.NOT_READY
        else Readiness.CANNOT_DETERMINE
    )
    return replace(
        verdict,
        readiness=state,
        reasons=verdict.reasons + tuple(waits) + tuple(unknown),
    )
