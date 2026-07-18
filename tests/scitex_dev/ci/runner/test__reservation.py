"""Unit tests for the scitex-hpc reservations CLI adapter.

No mocks: we pass a real fake ``hpc_runner`` callable (per PA-306 / STX-NM*)
that returns ``CompletedProcess``-shaped objects keyed by the reservations
verb, so the production code exercises its real JSON-parse + exit-code logic.
The fake doubles as a call-recorder so tests assert the exact argv handed to
``scitex-hpc``. One assertion per test (STX-TQ007); AAA markers per STX-TQ002.
"""

from __future__ import annotations

import json

import pytest

from scitex_dev.ci.runner import _reservation


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeHpc:
    """Programmable ``scitex-hpc`` CLI fake.

    ``responses`` maps the reservations verb (args[1], e.g. ``"get"``) to a
    ``_FakeCompletedProcess``. Records every argv in ``calls``.
    """

    def __init__(self, responses: dict[str, _FakeCompletedProcess]):
        self._responses = responses
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> _FakeCompletedProcess:
        self.calls.append(args)
        verb = args[1] if len(args) > 1 else ""
        if verb not in self._responses:
            raise AssertionError(f"unexpected reservations verb {verb!r}: {args}")
        return self._responses[verb]


def _blob(*, job_id: str = "", node: str = "", name: str = "ci-res") -> str:
    return json.dumps(
        {
            "id": f"spartan-{name}",
            "name": name,
            "host": "spartan",
            "job_id": job_id,
            "node": node,
            "submitted_at": "2026-06-21T00:00:00+00:00",
            "walltime_end": "",
            "persistent": True,
        }
    )


# ---------------------------------------------------------------------------
# get_state
# ---------------------------------------------------------------------------


def test_get_state_absent_on_exit_2():
    # Arrange — `reservations get` exits 2 when there is no lease file.
    fake = _FakeHpc(
        {"get": _FakeCompletedProcess(returncode=2, stderr="(no reservation ...)")}
    )
    # Act
    state = _reservation.get_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert
    assert state.present is False


def test_get_state_present_when_lease_file_exists():
    # Arrange
    fake = _FakeHpc(
        {"get": _FakeCompletedProcess(stdout=_blob(job_id="123", node="spartan-bm1"))}
    )
    # Act
    state = _reservation.get_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert
    assert state.present is True


def test_get_state_live_when_job_and_node_set():
    # Arrange — a healthy lease file carries job_id + node.
    fake = _FakeHpc(
        {"get": _FakeCompletedProcess(stdout=_blob(job_id="123", node="spartan-bm1"))}
    )
    # Act
    state = _reservation.get_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert
    assert state.live is True


def test_get_state_parses_node():
    # Arrange
    fake = _FakeHpc(
        {"get": _FakeCompletedProcess(stdout=_blob(job_id="123", node="spartan-bm1"))}
    )
    # Act
    state = _reservation.get_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert
    assert state.node == "spartan-bm1"


def test_get_state_not_live_when_node_missing():
    # Arrange — lease file exists but has no allocated node (still PENDING).
    fake = _FakeHpc({"get": _FakeCompletedProcess(stdout=_blob(job_id="123", node=""))})
    # Act
    state = _reservation.get_state("ci-res", hpc_runner=fake)
    # Assert
    assert state.live is False


def test_get_state_raises_on_unexpected_nonzero():
    # Arrange — rc 1 is a real failure, not the documented "missing" rc 2.
    fake = _FakeHpc({"get": _FakeCompletedProcess(returncode=1, stderr="boom")})
    # Act
    # Assert
    with pytest.raises(RuntimeError, match="reservations get"):
        _reservation.get_state("ci-res", hpc_runner=fake)


def test_get_state_passes_host_and_json_flags():
    # Arrange
    fake = _FakeHpc({"get": _FakeCompletedProcess(stdout=_blob(job_id="1", node="n"))})
    # Act
    _reservation.get_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert — exact argv: reservations get <name> --host spartan --json
    assert fake.calls[0] == [
        "reservations",
        "get",
        "ci-res",
        "--host",
        "spartan",
        "--json",
    ]


def test_get_state_omits_host_flag_when_unset():
    # Arrange
    fake = _FakeHpc({"get": _FakeCompletedProcess(stdout=_blob(job_id="1", node="n"))})
    # Act
    _reservation.get_state("ci-res", host=None, hpc_runner=fake)
    # Assert
    assert "--host" not in fake.calls[0]


# ---------------------------------------------------------------------------
# refresh_state
# ---------------------------------------------------------------------------


def test_refresh_state_live_after_rekey():
    # Arrange — refresh re-discovers a new job_id (the 7-day re-key path).
    fake = _FakeHpc(
        {
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="999", node="spartan-bm2")
            )
        }
    )
    # Act
    state = _reservation.refresh_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert
    assert state.live is True


def test_refresh_state_picks_up_new_job_id():
    # Arrange
    fake = _FakeHpc(
        {
            "refresh": _FakeCompletedProcess(
                stdout=_blob(job_id="999", node="spartan-bm2")
            )
        }
    )
    # Act
    state = _reservation.refresh_state("ci-res", host="spartan", hpc_runner=fake)
    # Assert
    assert state.job_id == "999"


def test_refresh_state_not_live_when_no_live_job_exit_2_no_json():
    # Arrange — refresh exits 2 with only a stderr notice when squeue finds
    # nothing live (the allocation died / walltime gap not yet bridged).
    fake = _FakeHpc(
        {"refresh": _FakeCompletedProcess(returncode=2, stderr="(no live job)")}
    )
    # Act
    state = _reservation.refresh_state("ci-res", hpc_runner=fake)
    # Assert
    assert state.live is False


def test_refresh_state_present_when_no_live_job():
    # Arrange — the lease file is still on disk; only the allocation is gone.
    fake = _FakeHpc(
        {"refresh": _FakeCompletedProcess(returncode=2, stderr="(no live job)")}
    )
    # Act
    state = _reservation.refresh_state("ci-res", hpc_runner=fake)
    # Assert
    assert state.present is True


def test_refresh_state_not_live_when_blob_has_empty_job_id():
    # Arrange — refresh cleared job_id/node (rc 0 but emptied blob).
    fake = _FakeHpc(
        {
            "refresh": _FakeCompletedProcess(
                returncode=0, stdout=_blob(job_id="", node="")
            )
        }
    )
    # Act
    state = _reservation.refresh_state("ci-res", hpc_runner=fake)
    # Assert
    assert state.live is False


def test_refresh_state_raises_on_unexpected_rc():
    # Arrange — rc 3 is neither success nor the documented "no live job" rc 2.
    fake = _FakeHpc({"refresh": _FakeCompletedProcess(returncode=3, stderr="boom")})
    # Act
    # Assert
    with pytest.raises(RuntimeError, match="reservations refresh"):
        _reservation.refresh_state("ci-res", hpc_runner=fake)


# ---------------------------------------------------------------------------
# build_book_args
# ---------------------------------------------------------------------------


def test_build_book_args_forces_persistent():
    # Arrange — persistent is the 7-day auto-resubmit; always on.
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host="spartan")
    # Assert
    assert "--persistent" in args


def test_build_book_args_is_non_interactive():
    # Arrange — cron context: no prompts.
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host="spartan")
    # Assert
    assert "-y" in args


def test_build_book_args_requests_json():
    # Arrange — callers parse the booked node from JSON.
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host="spartan")
    # Assert
    assert "--json" in args


def test_build_book_args_passes_host_first():
    # Arrange
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host="spartan")
    # Assert
    assert args[:2] == ["--host", "spartan"]


def test_build_book_args_maps_cpus():
    # Arrange
    res_cfg = {"cpus": 64}
    # Act
    args = _reservation.build_book_args(res_cfg, host=None)
    # Assert
    assert args[args.index("--cpus") + 1] == "64"


def test_build_book_args_maps_partition():
    # Arrange
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host=None)
    # Assert
    assert args[args.index("--partition") + 1] == "cascade"


def test_build_book_args_omits_unset_params():
    # Arrange — only partition; everything else deferred to scitex-hpc.
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host=None)
    # Assert
    assert "--cpus" not in args


def test_build_book_args_omits_host_when_unset():
    # Arrange
    res_cfg = {"partition": "cascade"}
    # Act
    args = _reservation.build_book_args(res_cfg, host=None)
    # Assert
    assert "--host" not in args


# ---------------------------------------------------------------------------
# book / cancel argv
# ---------------------------------------------------------------------------


def test_book_invokes_reservations_book_with_args():
    # Arrange
    fake = _FakeHpc(
        {"book": _FakeCompletedProcess(stdout=_blob(job_id="7", node="spartan-bm3"))}
    )
    book_args = ["--host", "spartan", "--persistent", "-y", "--json"]
    # Act
    _reservation.book("ci-res", book_args=book_args, hpc_runner=fake)
    # Assert
    assert fake.calls[0] == ["reservations", "book", "ci-res", *book_args]


def test_book_returns_booked_node():
    # Arrange
    fake = _FakeHpc(
        {"book": _FakeCompletedProcess(stdout=_blob(job_id="7", node="spartan-bm3"))}
    )
    # Act
    state = _reservation.book("ci-res", book_args=["--persistent"], hpc_runner=fake)
    # Assert
    assert state.node == "spartan-bm3"


def test_book_raises_on_failure():
    # Arrange
    fake = _FakeHpc(
        {"book": _FakeCompletedProcess(returncode=1, stderr="sbatch failed")}
    )
    # Act
    # Assert
    with pytest.raises(RuntimeError, match="reservations book"):
        _reservation.book("ci-res", book_args=["--persistent"], hpc_runner=fake)


def test_cancel_uses_missing_ok():
    # Arrange
    fake = _FakeHpc({"cancel": _FakeCompletedProcess(stdout="released")})
    # Act
    _reservation.cancel("ci-res", host="spartan", hpc_runner=fake)
    # Assert — non-interactive + tolerant of an already-gone lease.
    assert fake.calls[0] == [
        "reservations",
        "cancel",
        "ci-res",
        "--host",
        "spartan",
        "-y",
        "--missing-ok",
    ]


# EOF
