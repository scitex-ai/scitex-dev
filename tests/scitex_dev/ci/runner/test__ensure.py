"""Unit tests for ``scitex-dev ci runner ensure`` — the lifecycle SOLVER.

Covers the decision logic the SOLVER hinges on:
  * re-book when the reservation is absent or expired,
  * restart a runner that GitHub reports offline,
  * no-op when the reservation is healthy and N runners are online.

No mocks of our own code (PA-306 / STX-NM*): the lease/runner backends are
exercised through real fake callables —
  * ``hpc_runner``  — a programmable ``scitex-hpc`` CLI fake (verb → response),
  * ``gh_runner``   — returns a canned ``actions/runners`` list,
  * ``restart_fn``  — records which runners were (re)started instead of ssh'ing.
One assertion per test (STX-TQ007); AAA markers per STX-TQ002.
"""

from __future__ import annotations

import json

import pytest

from scitex_dev.ci.runner import _ensure, _reservation


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeHpc:
    """``scitex-hpc`` CLI fake — verb (args[1]) → ``_FakeCompletedProcess``."""

    def __init__(self, responses: dict[str, _FakeCompletedProcess]):
        self._responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> _FakeCompletedProcess:
        self.calls.append(args)
        verb = args[1] if len(args) > 1 else ""
        if verb not in self._responses:
            raise AssertionError(f"unexpected reservations verb {verb!r}: {args}")
        return self._responses[verb]

    def verbs(self) -> list[str]:
        return [c[1] for c in self.calls if len(c) > 1]


def _blob(*, job_id: str = "", node: str = "") -> str:
    return json.dumps(
        {
            "id": "spartan-ci-res",
            "name": "ci-res",
            "host": "spartan",
            "job_id": job_id,
            "node": node,
            "persistent": True,
        }
    )


def _gh_runner_for(runners: list[dict]):
    """Fake ``gh`` that returns ``runners`` as the ``actions/runners`` array."""

    def _runner(args: list[str]) -> _FakeCompletedProcess:
        return _FakeCompletedProcess(stdout=json.dumps(runners))

    return _runner


def _cfg(**reservation_overrides) -> dict:
    """Minimal runner config with a `reservation` block."""
    reservation = {
        "name": "ci-res",
        "cli": "scitex-hpc",
        "host": "spartan",
        "partition": "cascade",
        "cpus": 64,
    }
    reservation.update(reservation_overrides)
    return {
        "hpc": {
            "ssh_host": "spartan",
            "user": "u",
            "apptainer": "/x/apptainer",
            "sif": "/x.sif",
        },
        "runner": {
            "name": "spartan-cpu-runner-01",
            "labels": ["self-hosted", "scitex-ci"],
            "home": "/persist/runner-01",
            "wrap_log": "/persist/wrap.log",
        },
        "github": {"default_repo": "owner/repo"},
        "reservation": reservation,
    }


class _RestartRecorder:
    """Real fake for the restart seam — records (name, node) per call."""

    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def __call__(self, cfg: dict, runner: _ensure.DesiredRunner, node: str) -> None:
        self.calls.append((runner.name, node))


# ---------------------------------------------------------------------------
# decide_lease_action — the pure core
# ---------------------------------------------------------------------------


def test_decide_book_when_lease_absent():
    # Arrange — no lease file at all.
    get = _reservation.ReservationState.absent()
    # Act
    action = _ensure.decide_lease_action(get, None)
    # Assert
    assert action == "book"


def test_decide_noop_when_refresh_live():
    # Arrange — lease present and refresh re-keyed it to a live RUNNING node.
    get = _reservation.ReservationState(present=True, live=False)
    refreshed = _reservation.ReservationState(
        present=True, live=True, job_id="9", node="spartan-bm2"
    )
    # Act
    action = _ensure.decide_lease_action(get, refreshed)
    # Assert
    assert action == "noop"


def test_decide_rebook_when_present_but_not_live():
    # Arrange — lease file lingers but squeue finds no live job (expired).
    get = _reservation.ReservationState(present=True, live=False)
    refreshed = _reservation.ReservationState(present=True, live=False)
    # Act
    action = _ensure.decide_lease_action(get, refreshed)
    # Assert
    assert action == "rebook"


# ---------------------------------------------------------------------------
# offline_runner_names — the pure runner-health core
# ---------------------------------------------------------------------------


def test_offline_includes_missing_runner():
    # Arrange — desired runner not present in the repo's runner list at all.
    desired = [
        _ensure.DesiredRunner(
            name="spartan-cpu-runner-01", home="/h", repo="owner/repo", labels="l"
        )
    ]
    # Act
    offline = _ensure.offline_runner_names(desired, {"owner/repo": []})
    # Assert
    assert offline == ["spartan-cpu-runner-01"]


def test_offline_includes_runner_with_offline_status():
    # Arrange
    desired = [
        _ensure.DesiredRunner(name="r1", home="/h", repo="owner/repo", labels="l")
    ]
    runners = {"owner/repo": [{"name": "r1", "status": "offline"}]}
    # Act
    offline = _ensure.offline_runner_names(desired, runners)
    # Assert
    assert offline == ["r1"]


def test_offline_excludes_online_runner():
    # Arrange
    desired = [
        _ensure.DesiredRunner(name="r1", home="/h", repo="owner/repo", labels="l")
    ]
    runners = {"owner/repo": [{"name": "r1", "status": "online"}]}
    # Act
    offline = _ensure.offline_runner_names(desired, runners)
    # Assert
    assert offline == []


def test_offline_is_per_repo_scoped():
    # Arrange — an online runner of the SAME name under a DIFFERENT repo must
    # not satisfy our repo's desired runner.
    desired = [
        _ensure.DesiredRunner(name="r1", home="/h", repo="owner/repo", labels="l")
    ]
    runners = {"owner/other": [{"name": "r1", "status": "online"}]}
    # Act
    offline = _ensure.offline_runner_names(desired, runners)
    # Assert
    assert offline == ["r1"]


# ---------------------------------------------------------------------------
# desired_runners — pool resolution
# ---------------------------------------------------------------------------


def test_desired_runners_defaults_to_single_from_runner_block():
    # Arrange — no explicit pool.
    cfg = _cfg()
    # Act
    pool = _ensure.desired_runners(cfg)
    # Assert
    assert [d.name for d in pool] == ["spartan-cpu-runner-01"]


def test_desired_runners_expands_explicit_pool():
    # Arrange — two executors for parallelism.
    cfg = _cfg(
        runners=[
            {"name": "r1", "home": "/p/r1"},
            {"name": "r2", "home": "/p/r2"},
        ]
    )
    # Act
    pool = _ensure.desired_runners(cfg)
    # Assert
    assert [d.name for d in pool] == ["r1", "r2"]


def test_desired_runners_inherits_default_repo():
    # Arrange — pool entry omits repo → inherits github.default_repo.
    cfg = _cfg(runners=[{"name": "r1", "home": "/p/r1"}])
    # Act
    pool = _ensure.desired_runners(cfg)
    # Assert
    assert pool[0].repo == "owner/repo"


def test_desired_runners_requires_home_per_entry():
    # Arrange — each executor needs its own _work/install dir.
    cfg = _cfg(runners=[{"name": "r1"}])
    # Act
    # Assert
    with pytest.raises(Exception, match="home"):
        _ensure.desired_runners(cfg)


# ---------------------------------------------------------------------------
# run_ensure — full pass with real fakes (no mocks)
# ---------------------------------------------------------------------------


def test_run_ensure_books_when_reservation_absent():
    # Arrange — get exits 2 (absent) → book; booked node allocated; runner online.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(returncode=2, stderr="(no reservation ...)"),
            "book": _FakeCompletedProcess(stdout=_blob(job_id="1", node="spartan-bm9")),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    result = _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh)
    # Assert
    assert result.lease_action == "book"


def test_run_ensure_book_does_not_call_refresh_when_absent():
    # Arrange — absent lease must skip refresh (nothing to re-discover).
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(returncode=2, stderr="(no reservation ...)"),
            "book": _FakeCompletedProcess(stdout=_blob(job_id="1", node="spartan-bm9")),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh)
    # Assert
    assert "refresh" not in hpc.verbs()


def test_run_ensure_rebooks_when_expired():
    # Arrange — lease file present but refresh finds no live job → cancel+book.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="")),
            "refresh": _FakeCompletedProcess(returncode=2, stderr="(no live job)"),
            "cancel": _FakeCompletedProcess(stdout="released"),
            "book": _FakeCompletedProcess(stdout=_blob(job_id="6", node="spartan-bm8")),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    result = _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh)
    # Assert
    assert result.lease_action == "rebook"


def test_run_ensure_reboot_cancels_stale_lease_before_booking():
    # Arrange — scitex-hpc book refuses to overwrite; stale file must be cleared.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="")),
            "refresh": _FakeCompletedProcess(returncode=2, stderr="(no live job)"),
            "cancel": _FakeCompletedProcess(stdout="released"),
            "book": _FakeCompletedProcess(stdout=_blob(job_id="6", node="spartan-bm8")),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh)
    # Assert — cancel precedes book.
    assert hpc.verbs().index("cancel") < hpc.verbs().index("book")


def test_run_ensure_noop_when_healthy():
    # Arrange — refresh re-keys to a live node; the one runner is online.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="spartan-bm7")),
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="5", node="spartan-bm7")
            ),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    result = _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh)
    # Assert
    assert result.lease_action == "noop"


def test_run_ensure_noop_does_not_book():
    # Arrange — a healthy lease must NOT trigger a book.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="spartan-bm7")),
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="5", node="spartan-bm7")
            ),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh)
    # Assert
    assert "book" not in hpc.verbs()


def test_run_ensure_noop_does_not_restart_online_runner():
    # Arrange — healthy lease + online runner → restart_fn never called.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="spartan-bm7")),
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="5", node="spartan-bm7")
            ),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "online"}])
    recorder = _RestartRecorder()
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh, restart_fn=recorder)
    # Assert
    assert recorder.calls == []


def test_run_ensure_restarts_offline_runner_on_node():
    # Arrange — healthy lease, but the runner is offline → restart on the node.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="spartan-bm7")),
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="5", node="spartan-bm7")
            ),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "offline"}])
    recorder = _RestartRecorder()
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh, restart_fn=recorder)
    # Assert — restarted the right runner on the live node.
    assert recorder.calls == [("spartan-cpu-runner-01", "spartan-bm7")]


def test_run_ensure_reports_restarted_runner():
    # Arrange
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="spartan-bm7")),
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="5", node="spartan-bm7")
            ),
        }
    )
    gh = _gh_runner_for([{"name": "spartan-cpu-runner-01", "status": "offline"}])
    recorder = _RestartRecorder()
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    result = _ensure.run_ensure(
        cfg, pool, hpc_runner=hpc, gh_runner=gh, restart_fn=recorder
    )
    # Assert
    assert result.restarted == ["spartan-cpu-runner-01"]


def test_run_ensure_defers_restart_when_no_node_yet():
    # Arrange — fresh book, SLURM has not allocated a node yet (PENDING). The
    # offline runner cannot be restarted this pass; defer to the next tick.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(returncode=2, stderr="(no reservation ...)"),
            "book": _FakeCompletedProcess(stdout=_blob(job_id="1", node="")),
        }
    )
    gh = _gh_runner_for([])  # runner missing → offline
    recorder = _RestartRecorder()
    cfg = _cfg()
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh, restart_fn=recorder)
    # Assert — no restart attempted onto an empty node.
    assert recorder.calls == []


def test_run_ensure_restarts_only_offline_member_of_pool():
    # Arrange — two-runner pool; r1 online, r2 offline.
    hpc = _FakeHpc(
        {
            "get": _FakeCompletedProcess(stdout=_blob(job_id="5", node="spartan-bm7")),
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="5", node="spartan-bm7")
            ),
        }
    )
    gh = _gh_runner_for(
        [
            {"name": "r1", "status": "online"},
            {"name": "r2", "status": "offline"},
        ]
    )
    recorder = _RestartRecorder()
    cfg = _cfg(
        runners=[
            {"name": "r1", "home": "/p/r1"},
            {"name": "r2", "home": "/p/r2"},
        ]
    )
    pool = _ensure.desired_runners(cfg)
    # Act
    _ensure.run_ensure(cfg, pool, hpc_runner=hpc, gh_runner=gh, restart_fn=recorder)
    # Assert
    assert recorder.calls == [("r2", "spartan-bm7")]


# EOF
