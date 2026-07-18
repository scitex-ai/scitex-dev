#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for scitex_dev.runtime._periodic — supervised periodic asyncio loop.

No real wall-clock waits: the ``sleep`` seam is a fake coroutine that records
requested delays and, after a bounded number of ticks, injects
``asyncio.CancelledError`` to stop the loop deterministically. Coroutines are
driven with ``asyncio.run`` (the repo has pytest but NOT pytest-asyncio, so
there is no ``@pytest.mark.asyncio`` here). One assertion per test, AAA-marked,
per the repo's TQ001/TQ002/TQ007 test-quality rules.

Convention note: to keep each test at exactly one top-level assertion, the
expected ``CancelledError`` (raised by the fake sleep to stop the loop) is
swallowed INSIDE a ``_drain`` helper, so the test body itself never combines a
``pytest.raises`` with a follow-up ``assert``.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from scitex_dev.runtime import PeriodicTask, PeriodicTaskGroup
from scitex_dev.runtime._periodic import _env_gate_open


# --------------------------------------------------------------------------- #
# Test seams                                                                   #
# --------------------------------------------------------------------------- #
class FakeSleep:
    """A drop-in for ``asyncio.sleep`` that never waits real time.

    Records every requested delay. After ``stop_after`` invocations it raises
    ``asyncio.CancelledError`` — this is how a test caps an otherwise-infinite
    loop without real sleeping. It also yields control cooperatively so other
    tasks (e.g. group members) make progress between ticks.
    """

    def __init__(self, stop_after: int | None = None):
        self.delays: list[float] = []
        self.stop_after = stop_after
        self.calls = 0

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        self.calls += 1
        if self.stop_after is not None and self.calls >= self.stop_after:
            raise asyncio.CancelledError()
        await asyncio.sleep(0)


class RecordingLogger(logging.Logger):
    """Captures ``.exception`` calls so fail-loud logging is assertable."""

    def __init__(self):
        super().__init__("test.periodic")
        self.exceptions: list[str] = []

    def exception(self, msg, *args, **kwargs):  # noqa: D401
        self.exceptions.append(msg % args if args else msg)


class FakeToThread:
    """Records that the off-loop dispatch hook was used, then calls fn inline."""

    def __init__(self):
        self.called = 0

    async def __call__(self, fn, *args, **kwargs):
        self.called += 1
        return fn(*args, **kwargs)


class FixedRng:
    """Deterministic ``uniform`` for jitter tests."""

    def __init__(self, value: float):
        self.value = value

    def uniform(self, lo, hi):
        return self.value


def _drain(task: PeriodicTask) -> None:
    """Run ``task.run()`` to completion, swallowing the FakeSleep cancellation.

    The fake sleep stops the loop by raising ``CancelledError``; that is the
    expected terminator here (not the behaviour under test), so it is absorbed
    to leave the calling test with a single behavioural assertion.
    """

    async def _go():
        try:
            await task.run()
        except asyncio.CancelledError:
            pass

    asyncio.run(_go())


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# 1. Interval firing                                                          #
# --------------------------------------------------------------------------- #
def test_fires_once_per_tick_over_multiple_intervals():
    # Arrange
    hits = []
    sleep = FakeSleep(stop_after=3)  # 3 sleeps → 3 ticks, then cancel
    task = PeriodicTask(lambda: hits.append(1), interval=5.0, name="fire", sleep=sleep)
    # Act
    _drain(task)
    # Assert
    assert len(hits) == 3


def test_inter_tick_delay_equals_interval_without_jitter():
    # Arrange
    sleep = FakeSleep(stop_after=3)
    task = PeriodicTask(lambda: None, interval=5.0, name="fire", sleep=sleep)
    # Act
    _drain(task)
    # Assert
    assert sleep.delays == [5.0, 5.0, 5.0]


def test_initial_delay_is_first_sleep_before_any_tick():
    # Arrange
    sleep = FakeSleep(stop_after=2)
    task = PeriodicTask(
        lambda: None, interval=2.0, name="delayed", initial_delay=10.0, sleep=sleep
    )
    # Act
    _drain(task)
    # Assert
    assert sleep.delays[0] == 10.0


def test_jitter_adds_bounded_random_delay_to_interval():
    # Arrange
    sleep = FakeSleep(stop_after=1)
    task = PeriodicTask(
        lambda: None, interval=4.0, name="jit", jitter=1.5, sleep=sleep,
        rng=FixedRng(0.7),
    )
    # Act
    _drain(task)
    # Assert
    assert sleep.delays[0] == pytest.approx(4.7)


# --------------------------------------------------------------------------- #
# 2. Off-loop blocking IO dispatch                                            #
# --------------------------------------------------------------------------- #
def test_sync_fn_dispatched_off_loop_via_to_thread():
    # Arrange
    to_thread = FakeToThread()
    sleep = FakeSleep(stop_after=1)
    task = PeriodicTask(
        lambda: None, interval=1.0, name="sync", sleep=sleep, to_thread=to_thread
    )
    # Act
    _drain(task)
    # Assert
    assert to_thread.called == 1


def test_coro_fn_awaited_directly_not_via_to_thread():
    # Arrange
    to_thread = FakeToThread()

    async def work():
        return None

    sleep = FakeSleep(stop_after=1)
    task = PeriodicTask(
        work, interval=1.0, name="coro", sleep=sleep, to_thread=to_thread
    )
    # Act
    _drain(task)
    # Assert
    assert to_thread.called == 0


def test_coro_fn_actually_runs_each_tick():
    # Arrange
    hits = []

    async def work():
        hits.append(1)

    sleep = FakeSleep(stop_after=2)
    task = PeriodicTask(work, interval=1.0, name="coro", sleep=sleep)
    # Act
    _drain(task)
    # Assert
    assert hits == [1, 1]


# --------------------------------------------------------------------------- #
# 3. Env gate                                                                 #
# --------------------------------------------------------------------------- #
def test_env_gate_closed_when_unset():
    # Arrange
    environ: dict = {}
    # Act
    is_open = _env_gate_open("G", environ)
    # Assert
    assert is_open is False


@pytest.mark.parametrize("falsy", ["", "0", "false", "FALSE", "no", "off", "  off  "])
def test_env_gate_closed_when_falsy(falsy):
    # Arrange
    environ = {"G": falsy}
    # Act
    is_open = _env_gate_open("G", environ)
    # Assert
    assert is_open is False


@pytest.mark.parametrize("truthy", ["1", "true", "yes", "on", "anything"])
def test_env_gate_open_when_truthy(truthy):
    # Arrange
    environ = {"G": truthy}
    # Act
    is_open = _env_gate_open("G", environ)
    # Assert
    assert is_open is True


def test_env_gate_absent_is_always_open():
    # Arrange
    environ: dict = {}
    # Act
    is_open = _env_gate_open(None, environ)
    # Assert
    assert is_open is True


def test_env_gate_skips_fn_when_falsy():
    # Arrange
    hits = []
    sleep = FakeSleep(stop_after=2)
    task = PeriodicTask(
        lambda: hits.append(1), interval=1.0, name="gated-off",
        gate_env="MY_GATE", sleep=sleep, environ={"MY_GATE": "0"},
    )
    # Act
    _drain(task)
    # Assert
    assert hits == []


def test_env_gate_keeps_ticking_when_skipping():
    # Arrange
    sleep = FakeSleep(stop_after=2)
    task = PeriodicTask(
        lambda: None, interval=1.0, name="gated-off",
        gate_env="MY_GATE", sleep=sleep, environ={"MY_GATE": "0"},
    )
    # Act
    _drain(task)
    # Assert
    assert sleep.calls == 2


def test_env_gate_runs_fn_when_truthy():
    # Arrange
    hits = []
    sleep = FakeSleep(stop_after=2)
    task = PeriodicTask(
        lambda: hits.append(1), interval=1.0, name="gated-on",
        gate_env="MY_GATE", sleep=sleep, environ={"MY_GATE": "1"},
    )
    # Act
    _drain(task)
    # Assert
    assert hits == [1, 1]


# --------------------------------------------------------------------------- #
# 4. Fail-loud-on-error                                                       #
# --------------------------------------------------------------------------- #
def test_log_continue_keeps_looping_after_raise():
    # Arrange
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise RuntimeError("kaboom")

    sleep = FakeSleep(stop_after=3)
    task = PeriodicTask(
        boom, interval=1.0, name="boomer", on_error="log-continue",
        sleep=sleep, logger=RecordingLogger(),
    )
    # Act
    _drain(task)
    # Assert
    assert calls["n"] == 3


def test_log_continue_logs_each_failure():
    # Arrange
    log = RecordingLogger()

    def boom():
        raise RuntimeError("kaboom")

    sleep = FakeSleep(stop_after=3)
    task = PeriodicTask(
        boom, interval=1.0, name="boomer", on_error="log-continue",
        sleep=sleep, logger=log,
    )
    # Act
    _drain(task)
    # Assert
    assert len(log.exceptions) == 3


def test_log_raise_propagates_the_exception():
    # Arrange
    def boom():
        raise RuntimeError("fatal")

    sleep = FakeSleep(stop_after=5)
    task = PeriodicTask(
        boom, interval=1.0, name="fatal", on_error="log-raise",
        sleep=sleep, logger=RecordingLogger(),
    )
    # Act
    # Assert
    with pytest.raises(RuntimeError, match="fatal"):
        _run(task.run())


def test_log_raise_logs_once_before_propagating():
    # Arrange
    log = RecordingLogger()

    def boom():
        raise RuntimeError("fatal")

    sleep = FakeSleep(stop_after=5)
    task = PeriodicTask(
        boom, interval=1.0, name="fatal", on_error="log-raise",
        sleep=sleep, logger=log,
    )

    async def _go():
        try:
            await task.run()
        except RuntimeError:
            pass

    # Act
    _run(_go())
    # Assert
    assert len(log.exceptions) == 1


# --------------------------------------------------------------------------- #
# 5. Clean teardown-cancel                                                    #
# --------------------------------------------------------------------------- #
def test_cancel_stops_loop_promptly_mid_tick():
    # Arrange
    hits = []

    async def slow_start():
        hits.append("start")
        await asyncio.sleep(3600)  # cancel must land here, not after interval

    async def driver():
        task = asyncio.create_task(
            PeriodicTask(slow_start, interval=1.0, name="cancelme").run()
        )
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return hits

    # Act
    result = _run(driver())
    # Assert
    assert result == ["start"]


def test_cancel_is_reraised_not_swallowed():
    # Arrange
    async def slow_start():
        await asyncio.sleep(3600)

    async def driver():
        task = asyncio.create_task(
            PeriodicTask(slow_start, interval=1.0, name="cancelme").run()
        )
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return task.cancelled()

    # Act
    was_cancelled = _run(driver())
    # Assert
    assert was_cancelled is True


def test_cancel_from_fn_is_not_treated_as_fn_error():
    # Arrange
    log = RecordingLogger()

    async def cancels():
        raise asyncio.CancelledError()

    async def driver():
        task = asyncio.create_task(
            PeriodicTask(
                cancels, interval=1.0, name="cancel-in-fn",
                on_error="log-continue", logger=log,
            ).run()
        )
        try:
            await task
        except asyncio.CancelledError:
            pass
        return log.exceptions

    # Act
    logged = _run(driver())
    # Assert
    assert logged == []


# --------------------------------------------------------------------------- #
# 6. Supervisor / group                                                       #
# --------------------------------------------------------------------------- #
def test_group_runs_every_member():
    # Arrange
    a_hits, b_hits = [], []

    async def a():
        a_hits.append("a")
        await asyncio.sleep(3600)

    async def b():
        b_hits.append("b")
        await asyncio.sleep(3600)

    async def driver():
        group = PeriodicTaskGroup(
            [
                PeriodicTask(a, interval=1.0, name="a"),
                PeriodicTask(b, interval=1.0, name="b"),
            ]
        )
        await group.start()
        await asyncio.sleep(0)
        await group.stop()
        return a_hits + b_hits

    # Act
    ran = _run(driver())
    # Assert
    assert ran == ["a", "b"]


def test_group_stop_cancels_all_members():
    # Arrange
    async def work():
        await asyncio.sleep(3600)

    async def driver():
        group = PeriodicTaskGroup(
            [PeriodicTask(work, interval=1.0, name=f"m{i}") for i in range(3)]
        )
        await group.start()
        await asyncio.sleep(0)
        running = list(group._running)
        await group.stop()
        return all(t.done() for t in running)

    # Act
    all_done = _run(driver())
    # Assert
    assert all_done is True


def test_group_stop_clears_running_list():
    # Arrange
    async def work():
        await asyncio.sleep(3600)

    async def driver():
        group = PeriodicTaskGroup([PeriodicTask(work, interval=1.0, name="m")])
        await group.start()
        await asyncio.sleep(0)
        await group.stop()
        return group._running

    # Act
    running = _run(driver())
    # Assert
    assert running == []


def test_group_stop_is_safe_when_never_started():
    # Arrange
    group = PeriodicTaskGroup([PeriodicTask(lambda: None, interval=1, name="x")])

    async def driver():
        await group.stop()
        return group._running

    # Act
    running = _run(driver())
    # Assert
    assert running == []


def test_group_context_manager_runs_member():
    # Arrange
    hits = []

    async def work():
        hits.append(1)
        await asyncio.sleep(3600)

    async def driver():
        async with PeriodicTaskGroup([PeriodicTask(work, interval=1.0, name="cm")]):
            await asyncio.sleep(0)
        return hits

    # Act
    ran = _run(driver())
    # Assert
    assert ran == [1]


def test_group_context_manager_stops_on_exit():
    # Arrange
    async def work():
        await asyncio.sleep(3600)

    async def driver():
        group = PeriodicTaskGroup([PeriodicTask(work, interval=1.0, name="cm")])
        async with group:
            await asyncio.sleep(0)
        return group._running

    # Act
    running = _run(driver())
    # Assert
    assert running == []


def test_group_wait_reraises_member_death():
    # Arrange
    async def survivor():
        await asyncio.sleep(3600)

    def dying():
        raise RuntimeError("member died")

    async def driver():
        group = PeriodicTaskGroup(
            [
                PeriodicTask(survivor, interval=1.0, name="survivor"),
                PeriodicTask(
                    dying, interval=1.0, name="dying",
                    on_error="log-raise", logger=RecordingLogger(),
                ),
            ]
        )
        await group.start()
        await group.wait()

    # Act
    # Assert
    with pytest.raises(RuntimeError, match="member died"):
        _run(driver())


def test_group_wait_tears_down_survivors():
    # Arrange
    async def survivor():
        await asyncio.sleep(3600)

    def dying():
        raise RuntimeError("member died")

    async def driver():
        group = PeriodicTaskGroup(
            [
                PeriodicTask(survivor, interval=1.0, name="survivor"),
                PeriodicTask(
                    dying, interval=1.0, name="dying",
                    on_error="log-raise", logger=RecordingLogger(),
                ),
            ]
        )
        await group.start()
        try:
            await group.wait()
        except RuntimeError:
            pass
        return group._running

    # Act
    running = _run(driver())
    # Assert
    assert running == []


# --------------------------------------------------------------------------- #
# Validation                                                                  #
# --------------------------------------------------------------------------- #
def test_rejects_non_positive_interval():
    # Arrange
    factory = lambda: PeriodicTask(lambda: None, interval=0, name="x")
    # Act
    # Assert
    with pytest.raises(ValueError):
        factory()


def test_rejects_negative_initial_delay():
    # Arrange
    factory = lambda: PeriodicTask(lambda: None, interval=1, name="x", initial_delay=-1)
    # Act
    # Assert
    with pytest.raises(ValueError):
        factory()


def test_rejects_negative_jitter():
    # Arrange
    factory = lambda: PeriodicTask(lambda: None, interval=1, name="x", jitter=-1)
    # Act
    # Assert
    with pytest.raises(ValueError):
        factory()


def test_rejects_unknown_on_error_policy():
    # Arrange
    factory = lambda: PeriodicTask(lambda: None, interval=1, name="x", on_error="explode")
    # Act
    # Assert
    with pytest.raises(ValueError):
        factory()


def test_public_api_importable_from_package_root():
    # Arrange
    import scitex_dev.runtime as rt
    # Act
    names = (hasattr(rt, "PeriodicTask"), hasattr(rt, "PeriodicTaskGroup"))
    # Assert
    assert names == (True, True)


def test_public_api_importable_from_top_level():
    # Arrange
    import scitex_dev
    # Act
    names = (
        hasattr(scitex_dev, "PeriodicTask"),
        hasattr(scitex_dev, "PeriodicTaskGroup"),
    )
    # Assert
    assert names == (True, True)


# EOF
