"""`_emit` must survive losing the `scitex_dev.audit` logger-class name race.

`scitex_logging.getLogger` IS `logging.getLogger` — scitex-logging keeps
no registry of its own, it just calls `logging.setLoggerClass(SciTeXLogger)`
at import time. A logger's class is therefore decided by the
`setLoggerClass` state live when that NAME is first created, and
`Logger.manager` caches the instance forever. If anything creates
`scitex_dev.audit` through the stdlib first, `_emit` gets a plain
`logging.Logger` with no `.success`, and every auditor (`_project`,
`_django`, `_api`, `_summary`) dies with AttributeError.

No mocks. The poisoned logger here is a real `logging.Logger` built by the
real manager under real `setLoggerClass` state, handed to `emit` through
its real `logger=` parameter; the end-to-end arms run a real interpreter
with the real import ordering.

Assertions read `caplog` — the transport `_emit` actually uses. Asserting
on stdout via `capfd` would depend on ambient root-handler configuration,
which is import-order dependent (this is what made PR #417 pass locally
and fail in CI).
"""

from __future__ import annotations

import logging
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import scitex_dev
import scitex_dev._cli.audit._emit as emit_mod
from tests._child_env import with_loader_path

# The `src/` dir holding the scitex_dev package UNDER TEST, so the
# subprocess arms import the same tree this process imported — not
# whatever older copy happens to sit in site-packages.
_SRC = str(Path(scitex_dev.__file__).parents[1])
_DEGRADE_MARKER = "audit emit degraded"


def _levelnames_for(caplog, message: str) -> list[str]:
    """Level names of every captured record whose message is exactly `message`."""
    return [r.levelname for r in caplog.records if r.getMessage() == message]


def _degrade_notices(caplog) -> list[str]:
    """Messages of the captured WARNING+ records announcing the degrade."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.WARNING and _DEGRADE_MARKER in r.getMessage()
    ]


@pytest.fixture
def clean_degraded_flag():
    """`_degraded_reason` is process-global one-shot state; isolate each test."""
    original = emit_mod._degraded_reason
    emit_mod._degraded_reason = None
    yield
    emit_mod._degraded_reason = original


@pytest.fixture
def poisoned_logger():
    """A REAL plain `logging.Logger` created exactly as the race creates one.

    Driving `setLoggerClass` deliberately reproduces the true mechanism:
    the manager stamps whichever class is live at first creation of the name.
    """
    name = "scitex_dev_test.race.poisoned"
    logging.Logger.manager.loggerDict.pop(name, None)
    previous = logging.getLoggerClass()
    logging.setLoggerClass(logging.Logger)
    try:
        logger = logging.getLogger(name)
    finally:
        logging.setLoggerClass(previous)
    logger.propagate = True
    logger.setLevel(1)
    yield logger
    logging.Logger.manager.loggerDict.pop(name, None)


@pytest.fixture
def healthy_logger():
    """A REAL SciTeXLogger — name created while scitex-logging's class is live."""
    import scitex_logging

    name = "scitex_dev_test.race.healthy"
    logging.Logger.manager.loggerDict.pop(name, None)
    logger = scitex_logging.getLogger(name)
    logger.propagate = True
    logger.setLevel(1)
    yield logger
    logging.Logger.manager.loggerDict.pop(name, None)


# ---------------------------------------------------------------------------
# The mechanism itself
# ---------------------------------------------------------------------------


def test_stdlib_created_logger_lacks_the_success_method(poisoned_logger):
    """The race really does yield a logger with no `.success`."""
    # Arrange
    logger = poisoned_logger
    # Act
    has_success = hasattr(logger, "success")
    # Assert
    assert has_success is False


def test_stdlib_created_logger_is_a_plain_logger(poisoned_logger):
    """The poisoned instance is the stdlib class, not a SciTeXLogger."""
    # Arrange
    logger = poisoned_logger
    # Act
    cls = type(logger)
    # Assert
    assert cls is logging.Logger


def test_scitex_logging_created_logger_has_the_success_method(healthy_logger):
    """Winning the race yields a logger carrying the custom levels."""
    # Arrange
    logger = healthy_logger
    # Act
    has_success = hasattr(logger, "success")
    # Assert
    assert has_success is True


# ---------------------------------------------------------------------------
# The crash is gone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("level", ["info", "warning", "error", "success", "skip"])
def test_emit_does_not_raise_at_any_level_on_a_poisoned_logger(
    poisoned_logger, clean_degraded_flag, caplog, level
):
    """No AttributeError at any level.

    The old eager method table dereferenced `.success` on EVERY call, so
    even `emit("info", ...)` crashed. Reaching the assert proves no raise.
    """
    # Arrange
    caplog.set_level(1)
    body = f"body-{level}"
    # Act
    emit_mod.emit(level, body, logger=poisoned_logger)
    # Assert
    assert body in caplog.text


# ---------------------------------------------------------------------------
# The fallback preserves the level — it is not a downgrade
# ---------------------------------------------------------------------------


def test_poisoned_logger_still_emits_succ_levelname(
    poisoned_logger, clean_degraded_flag, caplog
):
    """Fallback keeps levelname SUCC rather than downgrading to INFO.

    scitex-logging registers level NUMBERS on the `logging` module
    globally, so `Logger.log(SUCCESS, ...)` renders identically.
    """
    # Arrange
    caplog.set_level(1)
    # Act
    emit_mod.emit("success", "audit passed", logger=poisoned_logger)
    # Assert
    assert _levelnames_for(caplog, "audit passed") == ["SUCC"]


def test_poisoned_logger_still_emits_warn_levelname(
    poisoned_logger, clean_degraded_flag, caplog
):
    """WARN survives the fallback too."""
    # Arrange
    caplog.set_level(1)
    # Act
    emit_mod.emit("warning", "audit warned", logger=poisoned_logger)
    # Assert
    assert _levelnames_for(caplog, "audit warned") == ["WARN"]


# ---------------------------------------------------------------------------
# CONTROL ARM — the healthy path is NOT downgraded to the fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level, expected_levelname",
    [("success", "SUCC"), ("warning", "WARN"), ("error", "ERRO"), ("info", "INFO")],
)
def test_healthy_logger_emits_full_level_names(
    healthy_logger, clean_degraded_flag, caplog, level, expected_levelname
):
    """CONTROL: the normal SciTeXLogger path keeps SUCC/WARN/ERRO.

    Without this arm, "always take the fallback" would pass as a fix.
    """
    # Arrange
    caplog.set_level(1)
    body = f"control-{level}"
    # Act
    emit_mod.emit(level, body, logger=healthy_logger)
    # Assert
    assert _levelnames_for(caplog, body) == [expected_levelname]


def test_healthy_logger_never_records_a_degraded_reason(
    healthy_logger, clean_degraded_flag, caplog
):
    """CONTROL: a healthy run must not mark itself degraded."""
    # Arrange
    caplog.set_level(1)
    # Act
    emit_mod.emit("success", "healthy", logger=healthy_logger)
    # Assert
    assert emit_mod.degraded_reason() is None


def test_healthy_logger_never_announces_a_degrade(
    healthy_logger, clean_degraded_flag, caplog
):
    """CONTROL: no degrade notice on the normal path."""
    # Arrange
    caplog.set_level(1)
    # Act
    emit_mod.emit("success", "healthy", logger=healthy_logger)
    # Assert
    assert _degrade_notices(caplog) == []


# ---------------------------------------------------------------------------
# The degrade is VISIBLE, not swallowed (verification doctrine §8)
# ---------------------------------------------------------------------------


def test_degradation_is_announced_at_warning_naming_the_ordering_problem(
    poisoned_logger, clean_degraded_flag, caplog
):
    """A degrade branch with no trace is where a hard failure hides."""
    # Arrange
    caplog.set_level(1)
    # Act
    emit_mod.emit("success", "audit passed", logger=poisoned_logger)
    # Assert
    assert "before scitex_logging was imported" in "".join(_degrade_notices(caplog))


def test_degradation_is_announced_only_once_per_process(
    poisoned_logger, clean_degraded_flag, caplog
):
    """One notice per process — not one per emitted line."""
    # Arrange
    caplog.set_level(1)
    # Act
    for _ in range(5):
        emit_mod.emit("success", "audit passed", logger=poisoned_logger)
    # Assert
    assert len(_degrade_notices(caplog)) == 1


def test_degraded_reason_names_the_audit_logger_for_callers(
    poisoned_logger, clean_degraded_flag, caplog
):
    """The degrade surfaces as a VALUE, where the result is read."""
    # Arrange
    caplog.set_level(1)
    # Act
    emit_mod.emit("success", "audit passed", logger=poisoned_logger)
    # Assert
    assert "scitex_dev.audit" in (emit_mod.degraded_reason() or "")


# ---------------------------------------------------------------------------
# End-to-end: the REAL import ordering, in a real interpreter
# ---------------------------------------------------------------------------


def _run_ordering_arm(stdlib_first: bool) -> str:
    """Run a real interpreter with/without the stdlib winning the name race."""
    script = textwrap.dedent(
        f"""
        import logging
        if {stdlib_first!r}:
            # Win the name race through the stdlib, exactly as a pytest
            # fixture calling caplog.set_level(..., logger="scitex_dev.audit")
            # does, BEFORE scitex_logging is ever imported.
            logging.getLogger("scitex_dev.audit")
        from scitex_dev._cli.audit._emit import emit, degraded_reason
        import scitex_dev._cli.audit._emit as m
        records = []
        class H(logging.Handler):
            def emit(self, r):
                records.append((r.levelname, r.getMessage()))
        m._logger.addHandler(H())
        m._logger.setLevel(1)
        for lvl in ("info", "warning", "error", "success", "skip"):
            emit(lvl, "body-" + lvl)
        print("LOGGER_TYPE", type(m._logger).__name__)
        print("DEGRADED", degraded_reason() is not None)
        for name, msg in records:
            if msg.startswith("body-"):
                print("REC", name, msg)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        # The minimal env is deliberate — this arm is about IMPORT ORDERING,
        # so anything that could reorder or silence an import is stated
        # rather than inherited. The loader path is not one of those things;
        # see tests/_child_env.py for why it must come through anyway.
        env=with_loader_path(
            {
                "PYTHONPATH": _SRC,
                "PATH": "/usr/bin:/bin",
                "SCITEX_DEV_LINTER_QUIET": "1",
            }
        ),
    )
    if result.returncode != 0:
        return f"SUBPROCESS_FAILED rc={result.returncode}\n{result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def stdlib_first_output() -> str:
    """One real run where the stdlib wins the `scitex_dev.audit` name."""
    return _run_ordering_arm(stdlib_first=True)


@pytest.fixture(scope="module")
def scitex_first_output() -> str:
    """One real run with the normal import ordering."""
    return _run_ordering_arm(stdlib_first=False)


def test_audit_emit_does_not_crash_when_stdlib_wins_the_name_race(
    stdlib_first_output,
):
    """The reported AttributeError must not reappear end to end."""
    # Arrange
    output = stdlib_first_output
    # Act
    crashed = "SUBPROCESS_FAILED" in output
    # Assert
    assert crashed is False, output


def test_stdlib_first_run_really_gets_the_poisoned_logger(stdlib_first_output):
    """Positive control: this arm genuinely reproduces the race."""
    # Arrange
    output = stdlib_first_output
    # Act
    line = "LOGGER_TYPE Logger" in output
    # Assert
    assert line is True, output


def test_stdlib_first_run_reports_itself_as_degraded(stdlib_first_output):
    """The end-to-end degrade is visible to the caller, not swallowed."""
    # Arrange
    output = stdlib_first_output
    # Act
    reported = "DEGRADED True" in output
    # Assert
    assert reported is True, output


def test_stdlib_first_run_still_emits_succ(stdlib_first_output):
    """Even poisoned, the success headline keeps its SUCC level name."""
    # Arrange
    output = stdlib_first_output
    # Act
    emitted = "REC SUCC body-success" in output
    # Assert
    assert emitted is True, output


def test_normal_ordering_gets_the_scitex_logger(scitex_first_output):
    """CONTROL: normal ordering keeps the real SciTeXLogger path."""
    # Arrange
    output = scitex_first_output
    # Act
    line = "LOGGER_TYPE SciTeXLogger" in output
    # Assert
    assert line is True, output


def test_normal_ordering_is_not_reported_as_degraded(scitex_first_output):
    """CONTROL: the fix must not mark a healthy process degraded."""
    # Arrange
    output = scitex_first_output
    # Act
    reported = "DEGRADED False" in output
    # Assert
    assert reported is True, output


@pytest.mark.parametrize(
    "expected_line",
    ["REC SUCC body-success", "REC WARN body-warning", "REC ERRO body-error"],
)
def test_normal_ordering_emits_the_full_headline_levels(
    scitex_first_output, expected_line
):
    """CONTROL: SUCC/WARN/ERRO all survive on the healthy end-to-end path."""
    # Arrange
    output = scitex_first_output
    # Act
    emitted = expected_line in output
    # Assert
    assert emitted is True, output
