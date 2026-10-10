"""Retire superseded queued PR checks through normal GitHub admission.

Current checks, running jobs and completed failure evidence are retained. The
shared job defaults to observation; its owning host explicitly selects apply.
"""

import json
import os
import re
import stat
import subprocess
import time

from .._core.streams import write_stream

REPOSITORIES = (
    "scitex-ai/scitex-agent-container",
    "scitex-ai/scitex-cards",
    "scitex-ai/claude-code-telegrammer",
    "scitex-ai/scitex-dev",
    "ywatanabe1989/.dotfiles",
)
MAX_CANCELLATIONS = 8
MAX_SECONDS = 45


def cancellation_candidate(run, pull, jobs):
    """Require an obsolete open-PR head and exclusively queued/finished jobs."""
    if run.get("event") != "pull_request" or run.get("status") != "queued":
        return False
    if pull.get("state") != "open":
        return False
    old = run.get("head_sha", "")
    current = pull.get("head", {}).get("sha", "")
    if (
        not all(
            isinstance(v, str) and re.fullmatch(r"[0-9a-f]{40}", v)
            for v in (old, current)
        )
        or old == current
    ):
        return False
    linked = run.get("pull_requests", [])
    if len(linked) != 1 or linked[0].get("number") != pull.get("number"):
        return False
    if jobs.get("total_count") != len(jobs.get("jobs", [])):
        return False
    rows = jobs.get("jobs", [])
    return (
        bool(rows)
        and any(v.get("status") == "queued" for v in rows)
        and all(v.get("status") in {"queued", "completed"} for v in rows)
    )


def _github(endpoint, deadline, *, cancel=False):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("PR queue job finite deadline reached")
    argv = ["gh", "api", endpoint]
    if cancel:
        argv += ["--method", "POST"]
    child = subprocess.run(
        argv, capture_output=True, text=True, timeout=min(5, remaining), check=False
    )
    if child.returncode:
        raise RuntimeError(
            f"normal GitHub API refused {endpoint}: exit {child.returncode}"
        )
    if len(child.stdout.encode()) > 2 * 1024 * 1024:
        raise ValueError("GitHub queue response exceeds bounded page")
    return json.loads(child.stdout) if child.stdout.strip() else None


def next_page(previous, total):
    """Cycle bounded pages so an ineligible oldest page cannot starve others."""
    last = max(1, (total + 19) // 20)
    current = min(previous, last) if previous is not None else last
    return current, current - 1 if current > 1 else last


def _same_lock(path, identity):
    current = path.lstat()
    if (current.st_dev, current.st_ino) != identity:
        raise ValueError("Owning job lock was replaced")


def run_once(*, apply=False, out=None):
    """Observe one rotating bounded page per repository; retire fresh candidates.

    Evidence goes through the federation's mandatory normal log sink. A timed
    out or refused cancel is UNKNOWN and never automatically retried in this
    invocation. No force-cancel, merge, workflow rerun or source edit is used.
    """
    import sys

    out = sys.stdout if out is None else out
    record = {
        "schema": "scitex.dev.pr-queue-retirement.v1",
        "apply": apply,
        "observed": [],
        "cancelled": [],
        "errors": [],
        "scope": list(REPOSITORIES),
        "queues": [],
        "completed_evidence_deleted": False,
    }
    deadline = time.monotonic() + MAX_SECONDS
    # Existing job logging handles durable output. One owning Linux controller
    # serializes the entire job through the same advisory file lock.
    import fcntl
    from pathlib import Path

    lock_path = Path(os.environ["SCITEX_DEV_PR_QUEUE_LOCK"])
    if not lock_path.is_absolute() or lock_path.parent.resolve() != lock_path.parent:
        raise ValueError("Require an explicit real absolute owning-host lock path")
    parent = lock_path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
        raise ValueError("Require a private uid-owned0700 owning-host lock directory")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        observed = os.fstat(fd)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != 0o600
        ):
            raise ValueError("Require a regular uid-owned0600 job lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_identity = (observed.st_dev, observed.st_ino)

        def same_lock():
            _same_lock(lock_path, lock_identity)

        cursor_path = lock_path.with_name(lock_path.name + ".pages.json")
        pages = {}
        if cursor_path.exists():
            cursor_fd = os.open(cursor_path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                cursor_stat = os.fstat(cursor_fd)
                if (
                    not stat.S_ISREG(cursor_stat.st_mode)
                    or cursor_stat.st_uid != os.getuid()
                    or stat.S_IMODE(cursor_stat.st_mode) != 0o600
                    or cursor_stat.st_size > 16384
                ):
                    raise ValueError("Invalid owning-host page cursor")
                pages = json.loads(os.read(cursor_fd, 16385))
            finally:
                os.close(cursor_fd)
            if (
                not isinstance(pages, dict)
                or set(pages) - set(REPOSITORIES)
                or any(type(v) is not int or v < 1 for v in pages.values())
            ):
                raise ValueError("Invalid repository page cursor")
        # Rotate the first repository each timer period to prevent a large queue
        # or API refusal on one owner from starving the other four indefinitely.
        first = int(time.time() // 300) % len(REPOSITORIES)
        for repository in REPOSITORIES[first:] + REPOSITORIES[:first]:
            page = _github(
                f"repos/{repository}/actions/runs?status=queued&event=pull_request&per_page=20",
                deadline,
            )
            total = page["total_count"]
            if type(total) is not int or total < 0:
                raise ValueError("Invalid actual queued-run count")
            oldest, following = next_page(pages.get(repository), total)
            if oldest > 1:
                page = _github(
                    f"repos/{repository}/actions/runs?status=queued"
                    f"&event=pull_request&per_page=20&page={oldest}",
                    deadline,
                )
            record["queues"].append(
                {
                    "repository": repository,
                    "observed_total": total,
                    "page": oldest,
                    "rows": len(page["workflow_runs"]),
                    "whole_queue_observed": (
                        oldest == 1
                        and total <= 20
                        and len(page["workflow_runs"]) == total
                    ),
                }
            )
            pages[repository] = following
            same_lock()
            temporary = cursor_path.with_name(cursor_path.name + f".{os.getpid()}")
            cursor_fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(cursor_fd, "w") as stream:
                json.dump(pages, stream, sort_keys=True)
                stream.flush()
                os.fsync(stream.fileno())
            same_lock()
            os.replace(temporary, cursor_path)
            for run in page["workflow_runs"]:
                links = run.get("pull_requests", [])
                if len(links) != 1:
                    continue
                number, run_id = links[0].get("number"), run.get("id")
                if type(number) is not int or type(run_id) is not int:
                    raise ValueError("Invalid normal GitHub run/PR identity")
                prefix = f"repos/{repository}"
                pull = _github(f"{prefix}/pulls/{number}", deadline)
                jobs = _github(
                    f"{prefix}/actions/runs/{run_id}/jobs?per_page=100", deadline
                )
                row = {
                    "repository": repository,
                    "run": run_id,
                    "pr": number,
                    "old_head": run["head_sha"],
                    "current_head": pull["head"]["sha"],
                    "candidate": cancellation_candidate(run, pull, jobs),
                    "jobs": [
                        {
                            k: v.get(k)
                            for k in ("id", "status", "conclusion", "runner_id")
                        }
                        for v in jobs["jobs"]
                    ],
                }
                record["observed"].append(row)
                if not apply or not row["candidate"]:
                    continue
                if len(record["cancelled"]) >= MAX_CANCELLATIONS:
                    record["continuation_required"] = True
                    break
                # Re-read all three normal objects immediately before effects.
                fresh_run = _github(f"{prefix}/actions/runs/{run_id}", deadline)
                fresh_pull = _github(f"{prefix}/pulls/{number}", deadline)
                fresh_jobs = _github(
                    f"{prefix}/actions/runs/{run_id}/jobs?per_page=100", deadline
                )
                if not cancellation_candidate(fresh_run, fresh_pull, fresh_jobs):
                    row["changed_before_effect"] = True
                    continue
                same_lock()
                # Persist the attempted normal action before the network call;
                # a timeout is not success. GitHub's cancel API has no CAS, so a
                # scheduling race remains explicit and no force path is used.
                write_stream(
                    json.dumps(
                        {"cancel_attempt": row, "scheduler_CAS_available": False}
                    ),
                    out,
                    flush=True,
                )
                _github(f"{prefix}/actions/runs/{run_id}/cancel", deadline, cancel=True)
                record["cancelled"].append(
                    {
                        **row,
                        "normal_cancel_accepted": True,
                        "terminal_cancellation_verified": False,
                    }
                )
                # Parent cancellation can change the enclosing run verdict;
                # retain each already completed job's exact verdict separately.
                retained = {
                    v["id"]: v.get("conclusion")
                    for v in fresh_jobs["jobs"]
                    if v["status"] == "completed"
                }
                after = _github(
                    f"{prefix}/actions/runs/{run_id}/jobs?per_page=100", deadline
                )
                actual = {
                    v["id"]: v.get("conclusion")
                    for v in after["jobs"]
                    if v["status"] == "completed"
                }
                if any(actual.get(k) != v for k, v in retained.items()):
                    raise ValueError("Completed job verdict retention not qualified")
                record["cancelled"][-1]["completed_job_verdicts_retained"] = retained
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        TimeoutError,
        subprocess.TimeoutExpired,
    ) as error:
        record["errors"].append(f"{type(error).__name__}: {error}")
    finally:
        os.close(fd)
        write_stream(json.dumps(record, sort_keys=True), out, flush=True)
    record["exit_code"] = int(bool(record["errors"]))
    return record
