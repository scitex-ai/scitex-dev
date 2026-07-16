"""Tests for the pure CI-log parser (``scitex_dev.ci.why._parse``).

No mocks. The parser is exercised on real-shaped GitHub-Actions log
STRINGS — timestamp prefixes, ``##[group]`` noise, a ``FAILURES`` block,
a ``short test summary info`` block, and a setup ``##[error]`` log. AAA,
one logical assertion per test.
"""

from __future__ import annotations

from scitex_dev.ci.why import (
    clean_log_line,
    parse_failed_log,
    parse_job_context,
    split_log_by_job,
)

# gh --log-failed prefixes each line "<job>\t<step>\t<ISO-timestamp>Z <content>".
_PJ = "pytest-matrix-on-ubuntu-py3.11"
_PS = "Run pytest"


def _line(job: str, step: str, ts: str, content: str) -> str:
    return f"{job}\t{step}\t{ts}Z {content}"


PYTEST_LOG = "\n".join(
    _line(_PJ, _PS, ts, content)
    for ts, content in [
        ("2026-07-15T10:00:00.1000000", "##[group]Run python -m pytest"),
        ("2026-07-15T10:00:00.2000000", "python -m pytest -v"),
        ("2026-07-15T10:00:00.3000000", "##[endgroup]"),
        ("2026-07-15T10:00:01.0000000", "=============== FAILURES ==============="),
        ("2026-07-15T10:00:01.1000000", "_______________ test_math _______________"),
        ("2026-07-15T10:00:01.3000000", "    def test_math():"),
        ("2026-07-15T10:00:01.4000000", ">       assert 3 == 4"),
        ("2026-07-15T10:00:01.5000000", "E       assert 3 == 4"),
        ("2026-07-15T10:00:01.7000000", "tests/test_math.py:5: AssertionError"),
        (
            "2026-07-15T10:00:02.0000000",
            "=========== short test summary info ===========",
        ),
        (
            "2026-07-15T10:00:02.1000000",
            "FAILED tests/test_math.py::test_math - AssertionError: assert 3 == 4",
        ),
        (
            "2026-07-15T10:00:02.2000000",
            "=========== 1 failed, 4 passed in 0.12s ===========",
        ),
        ("2026-07-15T10:00:02.3000000", "##[error]Process completed with exit code 1."),
    ]
)

_SJ = "no-hosted-runners-guard-on-self-hosted"
_SS = "Run astral-sh/setup-uv@v3"

SETUP_LOG = "\n".join(
    _line(_SJ, _SS, ts, content)
    for ts, content in [
        ("2026-07-15T15:59:17.6765113", "##[group]Run astral-sh/setup-uv@v3"),
        ("2026-07-15T15:59:17.6769300", "##[endgroup]"),
        (
            "2026-07-15T15:59:18.4499226",
            "ENOENT: no such file or directory, open '/data/_temp/99eb7246'",
        ),
        (
            "2026-07-15T15:59:48.7185987",
            "##[error]ENOENT: no such file or directory, open '/data/_temp/99eb7246'",
        ),
    ]
)

TAIL_LOG = "\n".join(
    _line("some-job-on-ubuntu-latest", "Build", ts, content)
    for ts, content in [
        ("2026-07-15T10:00:00.1000000", "##[group]Build"),
        ("2026-07-15T10:00:00.2000000", "compiling module foo"),
        ("2026-07-15T10:00:00.3000000", "##[endgroup]"),
        ("2026-07-15T10:00:00.4000000", "linker: undefined reference to bar"),
    ]
)


def test_clean_log_line_strips_job_prefix_and_timestamp():
    # Arrange
    raw = _line(_PJ, _PS, "2026-07-15T10:00:02.1000000", "FAILED tests/t.py::t - X")
    # Act
    cleaned = clean_log_line(raw)
    # Assert
    assert cleaned == "FAILED tests/t.py::t - X"


def test_clean_log_line_drops_group_markers():
    # Arrange
    raw = _line(_PJ, _PS, "2026-07-15T10:00:00.1000000", "##[group]Run x")
    # Act
    cleaned = clean_log_line(raw)
    # Assert
    assert cleaned is None


def test_clean_log_line_keeps_error_annotation():
    # Arrange
    raw = _line(_SJ, _SS, "2026-07-15T15:59:48.7185987", "##[error]ENOENT: boom")
    # Act
    cleaned = clean_log_line(raw)
    # Assert
    assert cleaned == "##[error]ENOENT: boom"


def test_split_log_by_job_separates_two_jobs():
    # Arrange
    text = "\n".join(
        [
            _line("job-a", "s", "2026-07-15T10:00:00.1000000", "a1"),
            _line("job-b", "s", "2026-07-15T10:00:00.2000000", "b1"),
            _line("job-a", "s", "2026-07-15T10:00:00.3000000", "a2"),
        ]
    )
    # Act
    groups = split_log_by_job(text)
    # Assert
    assert list(groups) == ["job-a", "job-b"]


def test_parse_job_context_dotted_pyversion_and_os():
    # Arrange
    name = "pytest-matrix-on-ubuntu-py3.11"
    # Act
    py, os_ = parse_job_context(name)
    # Assert
    assert (py, os_) == ("3.11", "ubuntu")


def test_parse_job_context_dashed_pyversion():
    # Arrange
    name = "import-smoke-on-ubuntu-py3-12"
    # Act
    py, _os = parse_job_context(name)
    # Assert
    assert py == "3.12"


def test_parse_job_context_self_hosted_has_no_python():
    # Arrange
    name = "no-hosted-runners-guard-on-self-hosted"
    # Act
    py, os_ = parse_job_context(name)
    # Assert
    assert (py, os_) == (None, "self-hosted")


def test_parse_failed_log_extracts_failing_test_id():
    # Arrange
    log = PYTEST_LOG
    # Act
    fail = parse_failed_log(log, job_name=_PJ)
    # Assert
    assert fail.failed_tests == [
        "FAILED tests/test_math.py::test_math - AssertionError: assert 3 == 4"
    ]


def test_parse_failed_log_extracts_assertion_line():
    # Arrange
    log = PYTEST_LOG
    # Act
    fail = parse_failed_log(log, job_name=_PJ)
    # Assert
    assert any("assert 3 == 4" in a for a in fail.assertions)


def test_parse_failed_log_strips_timestamp_and_group_noise():
    # Arrange
    log = PYTEST_LOG
    # Act
    fail = parse_failed_log(log, job_name=_PJ)
    # Assert
    leaked = [
        line
        for line in fail.failed_tests + fail.assertions
        if "2026-" in line or "##[group]" in line
    ]
    assert leaked == []


def test_parse_failed_log_carries_matrix_context():
    # Arrange
    log = PYTEST_LOG
    # Act
    fail = parse_failed_log(log, job_name=_PJ)
    # Assert
    assert (fail.py, fail.os) == ("3.11", "ubuntu")


def test_parse_failed_log_setup_failure_signal_is_annotation():
    # Arrange
    log = SETUP_LOG
    # Act
    fail = parse_failed_log(log, job_name=_SJ)
    # Assert
    assert fail.signal == "annotation"


def test_parse_failed_log_setup_failure_surfaces_enoent():
    # Arrange
    log = SETUP_LOG
    # Act
    fail = parse_failed_log(log, job_name=_SJ)
    # Assert
    assert any("ENOENT" in e for e in fail.errors)


def test_parse_failed_log_falls_back_to_tail_when_no_signal():
    # Arrange
    log = TAIL_LOG
    # Act
    fail = parse_failed_log(log, job_name="some-job-on-ubuntu-latest")
    # Assert
    assert "linker: undefined reference to bar" in fail.tail
