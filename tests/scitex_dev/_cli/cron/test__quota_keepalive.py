"""Unit tests for scitex_dev._cli.cron._quota_keepalive.

No mocks (PA-306 / STX-NM*). The self-gate is exercised against a real
temporary timestamp file under ``tmp_path``; the clock and the claude
invocation are passed as real callable seams so the production code runs
its real read/gate/write/dispatch path.
"""

from __future__ import annotations

import io

from scitex_dev._cli.cron import _jobs, _quota_keepalive


class _FakeCompletedProcess:
    """Real stand-in for subprocess.CompletedProcess (not a mock)."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _RecordingClaudeRunner:
    """A real callable that records the prompts it was asked to send."""

    def __init__(self, returncode: int = 0, stdout: str = "ok"):
        self.calls: list[str] = []
        self._returncode = returncode
        self._stdout = stdout

    def __call__(self, prompt: str) -> _FakeCompletedProcess:
        self.calls.append(prompt)
        return _FakeCompletedProcess(returncode=self._returncode, stdout=self._stdout)


# ---------------------------------------------------------------------------
# Registry — the JobSpec is registered with the expected shape
# ---------------------------------------------------------------------------


def test_registry_has_quota_keepalive_entry():
    # Arrange
    # Act
    # Assert
    assert "quota-keepalive" in _jobs.JOB_REGISTRY


def test_quota_keepalive_name_matches_registry_key():
    # Arrange
    # Act
    spec = _jobs.get_job("quota-keepalive")
    # Assert
    assert spec.name == "quota-keepalive"


def test_quota_keepalive_schedule_is_every_thirty_minutes():
    # Arrange
    # Act
    spec = _jobs.get_job("quota-keepalive")
    # Assert
    assert spec.schedule == "*/30 * * * *"


def test_quota_keepalive_command_invokes_scitex_dev_cron_exec():
    # Arrange
    # Act
    spec = _jobs.get_job("quota-keepalive")
    # Assert
    assert "scitex-dev cron exec quota-keepalive" in spec.command


def test_quota_keepalive_logs_under_dev_runtime_logs():
    # Arrange
    from scitex_dev._cli.cron import _job_commands

    # Act — the log path is owned by the verb now, not spelled into the
    # crontab line.
    log = _job_commands.log_path_for("quota-keepalive")
    # Assert — under runtime/, per the directive in jobs/_respawn.py:26.
    assert log.as_posix().endswith(
        "/.scitex/dev/runtime/logs/cron-quota-keepalive.log"
    )


def test_quota_keepalive_description_non_empty():
    # Arrange
    # Act
    spec = _jobs.get_job("quota-keepalive")
    # Assert
    assert spec.description.strip() != ""


def test_list_jobs_includes_quota_keepalive():
    # Arrange
    # Act
    names = [s.name for s in _jobs.list_jobs()]
    # Assert
    assert "quota-keepalive" in names


# ---------------------------------------------------------------------------
# is_due — the pure self-gate logic
# ---------------------------------------------------------------------------


def test_is_due_returns_true_when_never_fired():
    # Arrange
    last_fire = None
    # Act
    due = _quota_keepalive.is_due(last_fire, now=1000.0)
    # Assert
    assert due is True


def test_is_due_returns_false_when_last_fire_recent():
    # Arrange — fired 10 minutes ago, interval is 150
    now = 100_000.0
    last_fire = now - 10 * 60
    # Act
    due = _quota_keepalive.is_due(last_fire, now=now)
    # Assert
    assert due is False


def test_is_due_returns_true_at_exactly_the_interval_boundary():
    # Arrange — fired exactly 150 minutes ago
    now = 100_000.0
    last_fire = now - 150 * 60
    # Act
    due = _quota_keepalive.is_due(last_fire, now=now)
    # Assert
    assert due is True


def test_is_due_returns_true_when_well_past_the_interval():
    # Arrange — fired 3 hours ago
    now = 100_000.0
    last_fire = now - 180 * 60
    # Act
    due = _quota_keepalive.is_due(last_fire, now=now)
    # Assert
    assert due is True


# ---------------------------------------------------------------------------
# run_once — stale timestamp → fire
# ---------------------------------------------------------------------------


def test_run_once_fires_when_timestamp_file_absent(tmp_path):
    # Arrange
    ts = tmp_path / "quota-keepalive.last"
    runner = _RecordingClaudeRunner()
    # Act
    result = _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert result.fired is True


def test_run_once_sends_hello_prompt_when_due(tmp_path):
    # Arrange
    ts = tmp_path / "quota-keepalive.last"
    runner = _RecordingClaudeRunner()
    # Act
    _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert runner.calls == ["hello"]


def test_run_once_records_fire_timestamp_when_due(tmp_path):
    # Arrange
    ts = tmp_path / "quota-keepalive.last"
    runner = _RecordingClaudeRunner()
    # Act
    _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert float(ts.read_text().strip()) == 1_000_000.0


def test_run_once_fires_when_last_fire_is_stale(tmp_path):
    # Arrange — last fire was 3 hours ago (well past the 150-min gate)
    now = 2_000_000.0
    ts = tmp_path / "quota-keepalive.last"
    ts.write_text(f"{now - 180 * 60:.6f}\n")
    runner = _RecordingClaudeRunner()
    # Act
    result = _quota_keepalive.run_once(
        now=lambda: now,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert result.fired is True


# ---------------------------------------------------------------------------
# run_once — recent timestamp → skip
# ---------------------------------------------------------------------------


def test_run_once_skips_when_last_fire_recent(tmp_path):
    # Arrange — last fire was 30 minutes ago (under the 150-min gate)
    now = 2_000_000.0
    ts = tmp_path / "quota-keepalive.last"
    ts.write_text(f"{now - 30 * 60:.6f}\n")
    runner = _RecordingClaudeRunner()
    # Act
    result = _quota_keepalive.run_once(
        now=lambda: now,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert result.fired is False


def test_run_once_does_not_invoke_claude_when_skipping(tmp_path):
    # Arrange — last fire was 30 minutes ago
    now = 2_000_000.0
    ts = tmp_path / "quota-keepalive.last"
    ts.write_text(f"{now - 30 * 60:.6f}\n")
    runner = _RecordingClaudeRunner()
    # Act
    _quota_keepalive.run_once(
        now=lambda: now,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert runner.calls == []


def test_run_once_leaves_timestamp_unchanged_when_skipping(tmp_path):
    # Arrange — recent fire; record the original timestamp text
    now = 2_000_000.0
    ts = tmp_path / "quota-keepalive.last"
    original = f"{now - 30 * 60:.6f}\n"
    ts.write_text(original)
    runner = _RecordingClaudeRunner()
    # Act
    _quota_keepalive.run_once(
        now=lambda: now,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert ts.read_text() == original


# ---------------------------------------------------------------------------
# run_once — robustness: claude missing / errors must not crash
# ---------------------------------------------------------------------------


def test_run_once_returns_error_when_claude_missing(tmp_path):
    # Arrange — a runner that raises FileNotFoundError like a missing binary
    ts = tmp_path / "quota-keepalive.last"

    def _missing_claude(prompt: str):
        raise FileNotFoundError("claude")

    # Act
    result = _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=_missing_claude,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert result.error is not None


def test_run_once_does_not_write_timestamp_when_claude_missing(tmp_path):
    # Arrange — missing claude must not advance the gate (so the next tick retries)
    ts = tmp_path / "quota-keepalive.last"

    def _missing_claude(prompt: str):
        raise FileNotFoundError("claude")

    # Act
    _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=_missing_claude,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert not ts.exists()


def test_run_once_returns_error_on_nonzero_claude_exit(tmp_path):
    # Arrange — claude runs but exits non-zero
    ts = tmp_path / "quota-keepalive.last"
    runner = _RecordingClaudeRunner(returncode=1, stdout="boom")
    # Act
    result = _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert result.error is not None


def test_run_once_does_not_record_fire_on_nonzero_claude_exit(tmp_path):
    # Arrange — a non-zero exit must not advance the gate
    ts = tmp_path / "quota-keepalive.last"
    runner = _RecordingClaudeRunner(returncode=1, stdout="boom")
    # Act
    _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert not ts.exists()


def test_run_once_ignores_garbage_timestamp_and_fires(tmp_path):
    # Arrange — an unparseable timestamp file means "never fired"
    ts = tmp_path / "quota-keepalive.last"
    ts.write_text("not-a-float\n")
    runner = _RecordingClaudeRunner()
    # Act
    result = _quota_keepalive.run_once(
        now=lambda: 1_000_000.0,
        claude_runner=runner,
        ts_path=ts,
        out=io.StringIO(),
    )
    # Assert
    assert result.fired is True


# EOF
