"""Unit tests for scitex_dev._cli.cron._crontab.

Per the no-mocks rule (PA-306 / STX-NM*) we use plain dependency
injection via real callables — no monkeypatch, no `unittest.mock`.
"""

from __future__ import annotations

import pytest

from scitex_dev._cli.cron import _crontab


# ---------------------------------------------------------------------------
# managed_marker / build_line
# ---------------------------------------------------------------------------


def test_managed_marker_includes_name():
    # Arrange
    # Act
    marker = _crontab.managed_marker("ci-watch")
    # Assert
    assert marker == "# scitex-dev cron: ci-watch"


def test_managed_marker_rejects_space_in_name():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        _crontab.managed_marker("ci watch")


def test_build_line_contains_schedule_command_and_marker():
    # Arrange
    # Act
    line = _crontab.build_line(
        "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert line == (
        "*/10 * * * * scitex-dev cron run ci-watch # scitex-dev cron: ci-watch"
    )


def test_build_line_rejects_newline_in_command():
    # Arrange
    # Act
    # Assert
    with pytest.raises(ValueError):
        _crontab.build_line("ci-watch", "*/10 * * * *", "echo a\necho b")


# ---------------------------------------------------------------------------
# parse_managed
# ---------------------------------------------------------------------------


def test_parse_managed_returns_empty_for_no_marker():
    # Arrange
    text = "# unrelated\n0 0 * * * /bin/true\n"
    # Act
    out = _crontab.parse_managed(text)
    # Assert
    assert out == []


def test_parse_managed_returns_one_entry_with_correct_name():
    # Arrange
    text = (
        "0 0 * * * /bin/true\n"
        "*/10 * * * * scitex-dev cron run ci-watch # scitex-dev cron: ci-watch\n"
    )
    # Act
    out = _crontab.parse_managed(text)
    # Assert
    assert [m.name for m in out] == ["ci-watch"]


def test_parse_managed_returns_schedule_field():
    # Arrange
    text = "*/10 * * * * scitex-dev cron run ci-watch # scitex-dev cron: ci-watch\n"
    # Act
    out = _crontab.parse_managed(text)
    # Assert
    assert out[0].schedule == "*/10 * * * *"


def test_parse_managed_returns_command_field():
    # Arrange
    text = "*/10 * * * * scitex-dev cron run ci-watch # scitex-dev cron: ci-watch\n"
    # Act
    out = _crontab.parse_managed(text)
    # Assert
    assert out[0].command == "scitex-dev cron run ci-watch"


def test_parse_managed_handles_multiple_jobs():
    # Arrange
    text = (
        "*/10 * * * * a # scitex-dev cron: ci-watch\n"
        "0 * * * * b # scitex-dev cron: rotate-all\n"
    )
    # Act
    names = [m.name for m in _crontab.parse_managed(text)]
    # Assert
    assert names == ["ci-watch", "rotate-all"]


# ---------------------------------------------------------------------------
# upsert_managed / remove_managed — one assert per test
# ---------------------------------------------------------------------------


def test_upsert_when_absent_preserves_comment_line():
    # Arrange
    current = "# unrelated\n0 0 * * * /bin/true\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "# unrelated" in new


def test_upsert_when_absent_preserves_unrelated_job_line():
    # Arrange
    current = "# unrelated\n0 0 * * * /bin/true\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "0 0 * * * /bin/true" in new


def test_upsert_when_absent_appends_managed_marker():
    # Arrange
    current = "# unrelated\n0 0 * * * /bin/true\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "# scitex-dev cron: ci-watch" in new


def test_upsert_replace_keeps_exactly_one_managed_line():
    # Arrange
    current = "0 0 * * * /bin/true\n0 * * * * /old/cmd # scitex-dev cron: ci-watch\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert new.count("# scitex-dev cron: ci-watch") == 1


def test_upsert_replace_writes_new_schedule():
    # Arrange
    current = "0 * * * * /old/cmd # scitex-dev cron: ci-watch\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "*/10 * * * *" in new


def test_upsert_replace_drops_old_command_text():
    # Arrange
    current = "0 * * * * /old/cmd # scitex-dev cron: ci-watch\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "/old/cmd" not in new


def test_upsert_preserves_other_named_managed_lines():
    # Arrange
    current = "0 0 * * * /bin/true\n0 * * * * /other # scitex-dev cron: rotate-all\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "# scitex-dev cron: rotate-all" in new


def test_upsert_appends_target_managed_line_alongside_others():
    # Arrange
    current = "0 0 * * * /bin/true\n0 * * * * /other # scitex-dev cron: rotate-all\n"
    # Act
    new = _crontab.upsert_managed(
        current, "ci-watch", "*/10 * * * *", "scitex-dev cron run ci-watch"
    )
    # Assert
    assert "# scitex-dev cron: ci-watch" in new


def test_remove_counts_one_when_named_line_present():
    # Arrange
    current = (
        "0 0 * * * /bin/true\n"
        "0 * * * * /a # scitex-dev cron: ci-watch\n"
        "0 * * * * /b # scitex-dev cron: rotate-all\n"
    )
    # Act
    _new, removed = _crontab.remove_managed(current, "ci-watch")
    # Assert
    assert removed == 1


def test_remove_strips_only_named_marker():
    # Arrange
    current = (
        "0 0 * * * /bin/true\n"
        "0 * * * * /a # scitex-dev cron: ci-watch\n"
        "0 * * * * /b # scitex-dev cron: rotate-all\n"
    )
    # Act
    new, _removed = _crontab.remove_managed(current, "ci-watch")
    # Assert
    assert "# scitex-dev cron: ci-watch" not in new


def test_remove_preserves_other_named_marker():
    # Arrange
    current = (
        "0 0 * * * /bin/true\n"
        "0 * * * * /a # scitex-dev cron: ci-watch\n"
        "0 * * * * /b # scitex-dev cron: rotate-all\n"
    )
    # Act
    new, _removed = _crontab.remove_managed(current, "ci-watch")
    # Assert
    assert "# scitex-dev cron: rotate-all" in new


def test_remove_preserves_unrelated_lines():
    # Arrange
    current = "0 0 * * * /bin/true\n0 * * * * /a # scitex-dev cron: ci-watch\n"
    # Act
    new, _removed = _crontab.remove_managed(current, "ci-watch")
    # Assert
    assert "0 0 * * * /bin/true" in new


def test_remove_returns_zero_count_when_absent():
    # Arrange
    current = "0 0 * * * /bin/true\n"
    # Act
    _new, removed = _crontab.remove_managed(current, "ci-watch")
    # Assert
    assert removed == 0


def test_remove_returns_unchanged_text_when_absent():
    # Arrange
    current = "0 0 * * * /bin/true\n"
    # Act
    new, _removed = _crontab.remove_managed(current, "ci-watch")
    # Assert
    assert new == "0 0 * * * /bin/true\n"


# ---------------------------------------------------------------------------
# read_crontab / write_crontab (subprocess runner DI)
# ---------------------------------------------------------------------------


class _FakeCompletedProcess:
    """Minimal stand-in for subprocess.CompletedProcess."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_read_crontab_returns_stdout_when_rc_zero():
    # Arrange
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(returncode=0, stdout="# my cron\n")

    # Act
    out = _crontab.read_crontab(runner=fake_runner)
    # Assert
    assert out == "# my cron\n"


def test_read_crontab_returns_empty_when_rc_nonzero():
    # Arrange
    # `crontab -l` returns 1 for "no crontab for $USER" — treat as empty.
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr="no crontab for x")

    # Act
    out = _crontab.read_crontab(runner=fake_runner)
    # Assert
    assert out == ""


def test_write_crontab_passes_dash_argv_to_runner():
    # Arrange
    captured: dict = {}

    def fake_runner(args, *, input, **kwargs):
        captured["args"] = args
        captured["input"] = input
        return _FakeCompletedProcess(returncode=0)

    # Act
    _crontab.write_crontab("foo\nbar\n", runner=fake_runner)
    # Assert
    assert captured["args"] == ["crontab", "-"]


def test_write_crontab_passes_content_via_input():
    # Arrange
    captured: dict = {}

    def fake_runner(args, *, input, **kwargs):
        captured["args"] = args
        captured["input"] = input
        return _FakeCompletedProcess(returncode=0)

    # Act
    _crontab.write_crontab("foo\nbar\n", runner=fake_runner)
    # Assert
    assert captured["input"] == "foo\nbar\n"


def test_write_crontab_raises_on_nonzero():
    # Arrange
    def fake_runner(*args, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr="boom")

    # Act
    # Assert
    with pytest.raises(RuntimeError, match="boom"):
        _crontab.write_crontab("foo\n", runner=fake_runner)


# EOF
