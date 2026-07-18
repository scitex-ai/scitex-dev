"""Tests for ``scitex_dev._hooks.run_testmon_cli`` — the console-script shim.

The shim execs the bundled ``run_testmon.sh`` wrapper so pre-commit can use a
bare entry point. pre-commit does NOT shell-expand ``entry:``, so ``bash
$(scitex-dev hooks show-path run_testmon)`` cannot work there. Repos instead
use the console script ``scitex-dev-testmon`` (or ``python -m
scitex_dev._hooks.run_testmon_cli``), which execs the bundled wrapper with all
args forwarded.

Split out of ``test___init__.py`` so this suite mirrors its own
``run_testmon_cli.py`` src module (the wrapper-resolution tests that exercise
the ``_hooks`` package surface stay in ``test___init__.py``).
"""

from __future__ import annotations

import subprocess
import sys


class TestRunTestmonConsoleShim:
    """The shim execs the wrapper so pre-commit can use a bare entry.

    pre-commit does NOT shell-expand ``entry:``, so ``bash $(scitex-dev
    hooks show-path run_testmon)`` cannot work there. Repos instead use the
    console script ``scitex-dev-testmon`` (or ``python -m
    scitex_dev._hooks.run_testmon_cli``), which execs the bundled wrapper
    with all args forwarded.
    """

    def test_main_is_importable_and_callable(self):
        # Arrange
        from scitex_dev._hooks import run_testmon_cli
        # Act
        main = run_testmon_cli.main
        # Assert
        assert callable(main)

    def test_module_run_execs_wrapper_self_test(self):
        # Arrange — `python -m ...` must exec the wrapper, which self-tests.
        # Act
        proc = subprocess.run(
            [sys.executable, "-m", "scitex_dev._hooks.run_testmon_cli", "--self-test"],
            capture_output=True,
            text=True,
        )
        # Assert — exit 0 AND the wrapper's cache-keying line appears, proving
        # the shim reached run_testmon.sh and forwarded the `--self-test` arg.
        emitted = (proc.returncode, "cache dir keyed by (repo, pyXY)" in proc.stdout)
        assert emitted == (0, True), (
            f"`-m run_testmon_cli --self-test` must exec the wrapper and exit "
            f"0; got {emitted}; stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )
