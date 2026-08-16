#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# File: src/scitex_dev/_cli/cron/_ci_watch_cards.py
"""ci-watch: file a card when a workflow goes red.

THE IMPORT NAME IS `scitex_cards`, NOT `scitex_todo`. The retired name
is deleted by scitex-cards#859 on the operator's ruling that it must
not exist at all.

THAT RENAME IS NOT COSMETIC, because of the fallback below. A soft
dependency MISSING ON SOME HOSTS degrades there and works elsewhere --
which is what the try/except was written for. A soft dependency whose
NAME NO LONGER EXISTS degrades on EVERY host, permanently, and
`return None` is indistinguishable from "there was no card to file".
Leaving the old name would not have crashed ci-watch; it would have
SILENTLY STOPPED IT FILING CARDS fleet-wide, which is far harder to
notice than a crash. Flagged by scitex-cards BEFORE merging #859.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ._ci_watch_types import FailingRun  # noqa: F401  (used in annotations)

# ---------------------------------------------------------------------------
# scitex-todo creation layer (CI-fail → todo)
# ---------------------------------------------------------------------------
#
# When ci-watch spots a red workflow, we ALSO file a scitex-todo entry so
# the failure surfaces on the agent's board, not just in the dispatched
# fix-forward turn. Design notes:
#
#   * scitex-todo is a SOFT dependency. We lazy-import inside
#     :func:`_resolve_todo_api`; an ``ImportError`` (CI sandbox without
#     scitex-todo, fresh editable install, etc.) degrades to no-op, never
#     blocks the dispatch loop. Same fail-open spirit as the busy-probe.
#
#   * Idempotency: the (repo, workflow, head_sha) tuple is hashed into a
#     stable task id (see :func:`_todo_task_id_for`). A subsequent cron
#     round on the SAME failing SHA reuses the id; scitex-todo's
#     ``add_task`` raises ``TaskValidationError`` with the message
#     ``"duplicate task id ..."`` which we catch and treat as "already
#     filed" — no duplicate todos. proj-scitex-todo confirmed the
#     ``"duplicate task id"`` substring is stable (see ``_model.py:368``
#     in scitex-todo; if it ever shifts they grep our hook for sync).
#     No dedicated exit code exists yet (CLI uses click's catch-all
#     exit 1), so a substring match against the exception message is
#     the available identity signal.
#
#   * Mapping to scitex-todo's schema (proj-scitex-todo a2a, 2026-06-09):
#       - kind="task" (NOT "bug" — bug is not in VALID_KINDS; we prefix
#         the title with [CI-FAIL] instead so the operator can grep).
#       - status="pending"
#       - assignee=<owning sac agent>
#       - project=<repo basename>
#       - pr_url=<GitHub Actions run URL> (no --url flag exists; pr_url
#         is the closest free-form URL field)
#       - note=<markdown block with workflow / SHA / run URL>
#
#   * Auto-close on red→green recovery is intentionally OUT of scope
#     for v1 (lead 2026-06-09). Tracked as a follow-up.


@dataclass(frozen=True)
class _TodoApi:
    """Bundle of scitex-todo entry points needed by the hook.

    Lets tests substitute a hand-rolled fake (PA-306 / STX-NM*) for the
    `add_task` callable + the `validation_error_cls` type without
    `unittest.mock` or `monkeypatch`.
    """

    add_task: Callable[..., Any]
    validation_error_cls: type
    store_path: Path | None


def _resolve_todo_api(
    store_path: Path | None = None,
) -> _TodoApi | None:
    """Lazy-import scitex-todo. Returns ``None`` if not installed.

    Caller treats ``None`` as "scitex-todo unavailable → skip todo
    creation, keep going" (fail-open). This keeps scitex-todo a soft
    dependency: ci-watch's core (red detection + sac dispatch) works
    even on hosts that don't have scitex-todo installed.
    """
    try:
        from scitex_cards._paths import resolve_tasks_path
        from scitex_cards._store import (
            TaskValidationError,
            add_task,
        )
    except Exception:  # stx-allow: fallback (reason: scitex-cards is a soft dep)
        return None
    resolved = store_path if store_path is not None else resolve_tasks_path(None)
    return _TodoApi(
        add_task=add_task,
        validation_error_cls=TaskValidationError,
        store_path=resolved,
    )


_TODO_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _todo_task_id_for(repo: str, workflow: str, head_sha: str) -> str:
    """Stable id for the (repo, workflow, head_sha) tuple.

    Format: ``ci-fail-{repo-basename}-{workflow-slug}-{sha[:8]}``. Same
    failing SHA + workflow → same id → idempotent ``add_task`` (we catch
    ``TaskValidationError("duplicate task id ...")`` upstream). The
    workflow name is lowercased and stripped to ``[a-z0-9-]`` so spaces
    and matrix-row qualifiers (``pytest-matrix-on-ubuntu-py3.12``)
    round-trip safely through scitex-todo's id validation.
    """
    repo_slug = repo.split("/")[-1]
    workflow_slug = _TODO_SLUG_RE.sub("-", workflow.lower()).strip("-")
    short_sha = head_sha[:8] if head_sha else "nosha"
    return f"ci-fail-{repo_slug}-{workflow_slug}-{short_sha}"


def _create_todo_if_new(
    *,
    agent: str,
    repo: str,
    failing_run: FailingRun,
    todo_api: _TodoApi | None = None,
) -> bool:
    """File a CI-fail todo via the scitex-todo Python API.

    Returns ``True`` if a new todo was created, ``False`` if the
    (repo, workflow, head_sha) tuple was already on file (idempotent
    skip) OR scitex-todo is not importable (fail-open). Any other
    ``TaskValidationError`` (real schema breakage) re-raises.

    The substring match against ``"duplicate task id"`` is the
    identity signal proj-scitex-todo's CLI exposes today; if they ever
    add a dedicated exit code / exception subclass, swap this for the
    typed check. The string is hard-coded in scitex-todo's
    ``_model._validate_tasks`` (proj-scitex-todo a2a confirmed
    stability and committed to grep on rename).
    """
    api = todo_api if todo_api is not None else _resolve_todo_api()
    if api is None:
        return False
    task_id = _todo_task_id_for(repo, failing_run.workflow, failing_run.head_sha)
    project = repo.split("/")[-1]
    short_sha = failing_run.head_sha[:8] if failing_run.head_sha else "nosha"
    title = f"[CI-FAIL] {project} / {failing_run.workflow} @ {short_sha}"
    run_url = (
        f"https://github.com/{repo}/actions/runs/{failing_run.run_id}"
        if failing_run.run_id
        else ""
    )
    note = (
        f"Workflow: `{failing_run.workflow}`\n"
        f"SHA: `{failing_run.head_sha}`\n"
        f"Run: {run_url}"
    )
    try:
        api.add_task(
            api.store_path,
            id=task_id,
            title=title,
            status="pending",
            kind="task",
            project=project,
            assignee=agent,
            pr_url=run_url,
            note=note,
        )
        return True
    except api.validation_error_cls as exc:
        if "duplicate task id" in str(exc):
            return False
        raise




# EOF
