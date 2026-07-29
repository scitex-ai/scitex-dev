#!/usr/bin/env python3
"""The generated audit gate must be unmissable from a PARTIAL local run.

scitex-storage, 2026-07-29: CI red on 4 audit errors after a local
green, because they ran `tests/scitex_storage/` and the generated gate
lives at `tests/develop/test_audit.py` — outside the directory anyone
naturally runs. Second occurrence. Their conclusion: "I have a written
note to myself saying 'run the whole tests/ tree'. A note is not a
gate."

`tests/develop/` is load-bearing (see `_gate_guard`'s docstring for the
five path-addressed consumers), so the location stays and the MISS is
made impossible: a session that would otherwise report SUCCESS without
having collected the gate fails instead.

The acceptance criterion, asserted below on a REAL nested pytest run:
running ONLY the package test subdirectory must not produce an
unqualified green while the gate sits uncollected.

No mocks (PA-306 / STX-NM002): a real generated package tree under
tmp_path, run through a real pytest subprocess.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scitex_dev._cli.ecosystem._cmds._gate_guard import (
    GUARD_BEGIN,
    GUARD_END,
    OPT_OUT_ENV_VAR,
    render_conftest,
)

# A gate stand-in that always passes: this file exercises the GUARD, not
# the audit. If the guard is working, a run that omits this file cannot
# be green — and a run that includes it can.
_PASSING_GATE = (
    '"""Stand-in for the generated audit gate."""\n'
    "\n"
    "\n"
    "def test_audit_all_clean():\n"
    "    # Arrange\n"
    "    expected = True\n"
    "    # Act\n"
    "    actual = True\n"
    "    # Assert\n"
    "    assert actual is expected\n"
)

_PASSING_UNIT_TEST = (
    '"""An ordinary package unit test — always green."""\n'
    "\n"
    "\n"
    "def test_package_logic():\n"
    "    # Arrange\n"
    "    expected = 2\n"
    "    # Act\n"
    "    actual = 1 + 1\n"
    "    # Assert\n"
    "    assert actual == expected\n"
)


@pytest.fixture
def guarded_package(tmp_path):
    """A package tree with the gate + the generated guarded conftest."""
    root = tmp_path / "demo-pkg"
    (root / "tests" / "develop").mkdir(parents=True)
    (root / "tests" / "demo_pkg").mkdir(parents=True)
    (root / "tests" / "develop" / "test_audit.py").write_text(
        _PASSING_GATE, encoding="utf-8"
    )
    (root / "tests" / "demo_pkg" / "test_logic.py").write_text(
        _PASSING_UNIT_TEST, encoding="utf-8"
    )
    content, _action = render_conftest(None)
    (root / "tests" / "conftest.py").write_text(content, encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "demo-pkg"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    return root


def _run_pytest(
    root: Path,
    target: str,
    env_extra: dict | None = None,
    extra_args: tuple[str, ...] = (),
):
    """Run a real nested pytest against `root`, return the CompletedProcess."""
    import os

    env = {**os.environ, "PYTEST_ADDOPTS": ""}
    env.pop("SCITEX_DEV_ALLOW_PARTIAL_RUN", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            target,
            "-q",
            "-p",
            "no:cacheprovider",
            *extra_args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )


class TestPartialRunCannotReportGreen:
    """The acceptance criterion, on a real nested pytest session."""

    def test_package_subdir_only_run_fails(self, guarded_package):
        """`pytest tests/demo_pkg/` must NOT be green — the gate sat out.

        Both halves matter and are asserted separately here and below:
        a non-zero exit ALONE could come from anything, so
        `test_failure_names_the_reason` pins that this particular
        non-zero is the guard's.
        """
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/")
        # Assert
        assert proc.returncode != 0

    def test_failure_names_the_reason(self, guarded_package):
        """A red with no explanation just gets the guard deleted."""
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/")
        # Assert
        assert "AUDIT GATE DID NOT RUN IN THIS SESSION." in proc.stdout

    def test_failure_names_the_command_that_fixes_it(self, guarded_package):
        """The message must carry the whole-tree command."""
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/")
        # Assert
        assert "pytest tests/" in proc.stdout

    def test_failure_names_the_opt_out(self, guarded_package):
        """An escape hatch nobody can find is not an escape hatch."""
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/")
        # Assert
        assert OPT_OUT_ENV_VAR in proc.stdout


class TestGuardDoesNotFireWhenItShouldNot:
    """Positive controls — the guard must stay out of the way otherwise."""

    def test_whole_tree_run_is_green(self, guarded_package):
        """`pytest tests/` collects the gate, so nothing fires."""
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/")
        # Assert
        assert proc.returncode == 0

    def test_explicit_opt_out_allows_the_partial_green(self, guarded_package):
        """A named, per-run opt-out is honoured.

        Asserted on the GUARD'S OWN OUTPUT rather than on the exit code:
        the contract here is "the guard did not fire", and a process
        exit code can go non-zero for reasons that have nothing to do
        with this guard (observed once in this suite: the child was
        SIGTERMed by the environment after pytest had already reported
        `1 passed`). The banner's absence measures the contract; the
        exit code measures the contract plus the weather.
        """
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/", env_extra={OPT_OUT_ENV_VAR: "1"})
        # Assert
        assert "AUDIT GATE DID NOT RUN IN THIS SESSION." not in proc.stdout

    def test_repo_without_a_gate_is_not_gated(self, guarded_package):
        """No gate installed → nothing to miss → the guard is inert."""
        # Arrange
        (guarded_package / "tests" / "develop" / "test_audit.py").unlink()
        # Act
        proc = _run_pytest(guarded_package, "tests/demo_pkg/")
        # Assert
        assert proc.returncode == 0


xdist = pytest.importorskip(
    "xdist",
    reason="pytest-xdist is what `pytest tests/ -n auto` (this repo's CI) uses; "
    "without it the parallel-run contract cannot be measured at all",
)


class TestGuardUnderXdist:
    """`pytest tests/ -n auto` — the shape this repo's own CI runs.

    Under xdist the CONTROLLER never collects (workers do), so a guard
    that only records collection leaves the controller's flag False —
    and the controller is the process whose ``pytest_sessionfinish``
    sets the session exit status. Measured on scitex-dev PR #448 before
    this fix: `pytest tests/ -n auto` reported `5183 passed` and exited
    1, claiming the gate never ran while the gate's own PASS was in the
    report stream the controller had just received.
    """

    def test_whole_tree_parallel_run_is_green(self, guarded_package):
        """The gate ran and passed, so the guard must not fire."""
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/", extra_args=("-n", "2"))
        # Assert
        assert proc.returncode == 0

    def test_whole_tree_parallel_run_does_not_claim_the_gate_was_missed(
        self, guarded_package
    ):
        """The exit code alone could be non-zero for unrelated reasons.

        This pins that the specific claim — "the gate did not run" — is
        not made about a session in which the gate demonstrably ran.
        """
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/", extra_args=("-n", "2"))
        # Assert
        assert "AUDIT GATE DID NOT RUN IN THIS SESSION." not in proc.stdout

    def test_partial_parallel_run_still_fails(self, guarded_package):
        """Positive control: the guard must still bite under xdist.

        Making the controller trust the report stream must not be a way
        of switching the guard off for every parallel run.
        """
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/", extra_args=("-n", "2"))
        # Assert
        assert proc.returncode != 0

    def test_partial_parallel_run_names_the_reason(self, guarded_package):
        """…and says why, in the parallel case too."""
        # Arrange
        root = guarded_package
        # Act
        proc = _run_pytest(root, "tests/demo_pkg/", extra_args=("-n", "2"))
        # Assert
        assert "AUDIT GATE DID NOT RUN IN THIS SESSION." in proc.stdout


class TestGuardReachesRepositoriesThatAlreadyHaveAConftest:
    """The previous behaviour skipped an existing conftest entirely.

    Nearly every adopted repo has one, so skipping them would have left
    the guard reaching only brand new repos — the same accidental
    opt-in the guard exists to remove.
    """

    def test_existing_conftest_gains_the_guard(self):
        """The block is APPENDED, not substituted for the user's file."""
        # Arrange
        existing = '"""My fixtures."""\n\nimport pytest\n'
        # Act
        content, _action = render_conftest(existing)
        # Assert
        assert GUARD_BEGIN in content

    def test_existing_conftest_content_is_preserved(self):
        """A generator that eats your fixtures gets removed from CI."""
        # Arrange
        existing = '"""My fixtures."""\n\nimport pytest\n'
        # Act
        content, _action = render_conftest(existing)
        # Assert
        assert '"""My fixtures."""' in content

    def test_appending_reports_the_update(self):
        """Silent edits to a user-owned file are not acceptable."""
        # Arrange
        existing = '"""My fixtures."""\n'
        # Act
        _content, action = render_conftest(existing)
        # Assert
        assert action == "updated"

    def test_rerunning_is_idempotent(self):
        """A second install must not stack a second copy of the block."""
        # Arrange
        once, _a = render_conftest('"""My fixtures."""\n')
        # Act
        twice, _b = render_conftest(once)
        # Assert
        assert twice.count(GUARD_BEGIN) == 1

    def test_rerunning_reports_no_change(self):
        """An unchanged file must not be rewritten."""
        # Arrange
        once, _a = render_conftest('"""My fixtures."""\n')
        # Act
        _twice, action = render_conftest(once)
        # Assert
        assert action == "current"

    def test_a_stale_block_is_refreshed_in_place(self):
        """Only the marked block is replaced; the rest is untouched."""
        # Arrange
        stale = (
            '"""My fixtures."""\n\n'
            f"{GUARD_BEGIN}\n# an older guard\n{GUARD_END}\n\n"
            "def my_helper():\n    return 1\n"
        )
        # Act
        content, _action = render_conftest(stale)
        # Assert
        assert "def my_helper():" in content

    def test_refresh_drops_the_stale_body(self):
        """A refresh must not leave the old implementation behind."""
        # Arrange
        stale = f'"""My fixtures."""\n\n{GUARD_BEGIN}\n# an older guard\n{GUARD_END}\n'
        # Act
        content, _action = render_conftest(stale)
        # Assert
        assert "# an older guard" not in content

    def test_generated_conftest_is_valid_python(self):
        """A conftest that does not parse breaks every run in the repo."""
        # Arrange
        import ast

        content, _action = render_conftest(None)
        # Act
        parsed = ast.parse(content)
        # Assert
        assert isinstance(parsed, ast.Module)
