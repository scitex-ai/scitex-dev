"""A CLI invocation inside a pytest run must not emit the drift warning.

The 0.57.0 release was blocked by this, on all three matrix legs::

    FAILED tests/scitex_dev/_cli/test__hosts.py::test_resolve_field_kind_prints_value
    E   AssertionError: assert 'WARN: editab...b)\\nhpc-login' == 'hpc-login'
    E   + WARN: editable scitex-dev: HEAD (b17f06f9) is 2 commit(s) behind its
    E     remote — run: git -C ... pull --ff-only  (suppress: ...)
    E     hpc-login

Nothing was wrong with `host resolve`. `main()` had grown a SECOND
`emit_if_drift` call — unguarded, above the `PYTEST_CURRENT_TEST` guard that
exists precisely to stop this. The emitter is warn-ONCE per process, so the
first call site is the only one that ever speaks: the unguarded one took the
emission and the guard below it became dead code without being edited.

Why a release run is where it surfaced, and PR gates never saw it: the drift
check fires only for an EDITABLE install whose checkout is BEHIND its remote.
A release job builds from a TAG, and every commit that lands on `develop`
after the tag is cut leaves that tagged tree legitimately behind — so the
warning is not a malfunction, it is correct and simply belongs on a terminal
rather than inside another test's captured output.

No mocks. `emit_if_drift`'s warn-once latch is real state, and clearing it is
how you ask "did THIS invocation run the emitter" instead of "has anything in
this worker ever run it".
"""

from __future__ import annotations

import contextlib
import os

import pytest

pytest.importorskip("click")

from click.testing import CliRunner

from scitex_dev._cli._root import main
from scitex_dev._release.check_editable_drift import (
    _SUBPROCESS_MARKER,
    emit_if_drift,
)


@contextlib.contextmanager
def _latch_cleared():
    """Clear the warn-once latch (in-process flag + subprocess env marker).

    Both are restored afterwards, so this measures one invocation without
    changing what any later test in the same worker observes.
    """
    had_flag = hasattr(emit_if_drift, "_emitted")
    prev_flag = getattr(emit_if_drift, "_emitted", None)
    prev_env = os.environ.get(_SUBPROCESS_MARKER)
    with contextlib.suppress(AttributeError):
        del emit_if_drift._emitted
    os.environ.pop(_SUBPROCESS_MARKER, None)
    try:
        yield
    finally:
        if had_flag:
            emit_if_drift._emitted = prev_flag
        else:
            with contextlib.suppress(AttributeError):
                del emit_if_drift._emitted
        if prev_env is None:
            os.environ.pop(_SUBPROCESS_MARKER, None)
        else:
            os.environ[_SUBPROCESS_MARKER] = prev_env


def _emitter_ran_during(args: list[str], *, under_pytest: bool) -> bool:
    """Invoke the CLI and report whether `emit_if_drift` was reached.

    `under_pytest=False` hides `$PYTEST_CURRENT_TEST` for the duration of the
    call — the one thing `main`'s guard keys on — so the same measurement can
    be taken on both sides of the guard.
    """
    saved = os.environ.get("PYTEST_CURRENT_TEST")
    if not under_pytest:
        os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        with _latch_cleared():
            CliRunner().invoke(main, args)
            return bool(getattr(emit_if_drift, "_emitted", False))
    finally:
        if saved is not None:
            os.environ["PYTEST_CURRENT_TEST"] = saved


def test_cli_invocation_under_pytest_does_not_reach_the_drift_emitter():
    """The regression. Red with a second, unguarded call site in `main`."""
    # Arrange
    args = ["host"]
    # Act
    ran = _emitter_ran_during(args, under_pytest=True)
    # Assert
    assert ran is False


def test_cli_invocation_outside_pytest_does_reach_the_drift_emitter():
    """The control: without it the test above passes for any reason at all.

    It fails if `main` stops calling the emitter altogether — i.e. if the
    warning were "fixed" by deleting it rather than by placing it correctly.
    """
    # Arrange
    args = ["host"]
    # Act
    ran = _emitter_ran_during(args, under_pytest=False)
    # Assert
    assert ran is True


# EOF
