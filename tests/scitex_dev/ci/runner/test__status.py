"""Tests for the reservation-aware lease backend in ``_status``.

Mirrors ``src/scitex_dev/ci/runner/_status.py`` (PS-204 §2 test-file mirroring).

When the config names a scitex-hpc ``reservation``, the shared ``_lease_status``
helper (used by ``status`` AND ``preflight``) must report the reservation's live
allocation in the legacy ``{"jobs": [...]}`` shape instead of KeyError-ing on the
now-optional ``ci_lease`` block. No mocks: a real fake ``scitex-hpc`` CLI runner
drives ``_reservation_lease_status``. One assertion per test (STX-TQ007);
AAA markers (STX-TQ002).
"""

from __future__ import annotations

import json

from scitex_dev.ci.runner import _status


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _refresh_blob(*, job_id: str, node: str) -> str:
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


def _hpc_for(proc: _FakeCompletedProcess):
    def _runner(args: list[str]) -> _FakeCompletedProcess:
        return proc

    return _runner


_CFG = {
    "hpc": {"ssh_host": "spartan"},
    "reservation": {"name": "ci-res", "cli": "scitex-hpc", "host": "spartan"},
}


# ---------------------------------------------------------------------------
# _lease_label
# ---------------------------------------------------------------------------


def test_lease_label_uses_reservation_name():
    # Arrange
    cfg = {"reservation": {"name": "spartan-cpu-64-cores-256-ram"}}
    # Act
    label = _status._lease_label(cfg)
    # Assert
    assert label == "reservation spartan-cpu-64-cores-256-ram"


def test_lease_label_falls_back_to_ci_lease_jobname():
    # Arrange — no reservation block → legacy jobname.
    cfg = {"ci_lease": {"jobname": "scitex-ci-lease"}}
    # Act
    label = _status._lease_label(cfg)
    # Assert
    assert label == "name=scitex-ci-lease"


# ---------------------------------------------------------------------------
# _reservation_lease_status — maps a live reservation to a RUNNING jobs row
# ---------------------------------------------------------------------------


def test_reservation_lease_status_reports_running_when_live():
    # Arrange — refresh re-discovers a live allocation.
    fake = _hpc_for(
        _FakeCompletedProcess(stdout=_refresh_blob(job_id="42", node="spartan-bm5"))
    )
    # Act
    out = _status._reservation_lease_status(_CFG, _CFG["reservation"], hpc_runner=fake)
    # Assert — one RUNNING row so preflight's check-1 passes.
    assert out["jobs"][0]["state"] == "RUNNING"


def test_reservation_lease_status_reports_jobid_when_live():
    # Arrange
    fake = _hpc_for(
        _FakeCompletedProcess(stdout=_refresh_blob(job_id="42", node="spartan-bm5"))
    )
    # Act
    out = _status._reservation_lease_status(_CFG, _CFG["reservation"], hpc_runner=fake)
    # Assert
    assert out["jobs"][0]["jobid"] == "42"


def test_reservation_lease_status_empty_when_not_live():
    # Arrange — refresh found no live job (rc 2, allocation died).
    fake = _hpc_for(_FakeCompletedProcess(returncode=2, stderr="(no live job)"))
    # Act
    out = _status._reservation_lease_status(_CFG, _CFG["reservation"], hpc_runner=fake)
    # Assert — zero rows → preflight reports "no RUNNING CI lease".
    assert out["jobs"] == []


def test_reservation_lease_status_surfaces_error():
    # Arrange — an unexpected scitex-hpc failure becomes an error report.
    fake = _hpc_for(_FakeCompletedProcess(returncode=1, stderr="boom"))
    # Act
    out = _status._reservation_lease_status(_CFG, _CFG["reservation"], hpc_runner=fake)
    # Assert
    assert "error" in out


# EOF
