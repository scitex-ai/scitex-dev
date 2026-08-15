"""The in-SIF CI wrappers may never `rm -rf` their scratch path UNGUARDED.

WHY THIS EXISTS. Each of ``.github/ci/{run,build,publish}-in-sif.sh`` builds a
per-run scratch directory and deletes it with ``rm -rf``. Today the name is a
literal ``/tmp/…`` prefix plus interpolated run ids, so it cannot come back
empty — and that is exactly the state this file is pinning, not a reason to
skip the guard. scitex-agent-container's wrappers started from this identical
shape and later moved the name into a helper function in a DIFFERENT file, at
which point "always non-empty" stopped being visible from the deletion site.

WHAT AN EMPTY VALUE DOES, measured on GNU coreutils 9.4::

    $ bash -c 'set -euo pipefail; V=""; rm -rf "$V"; echo REACHED'
    REACHED
    rc=0

``-f`` treats the empty operand as a nonexistent file, so the command SUCCEEDS
SILENTLY. ``set -euo pipefail`` catches nothing, the script continues with
``TMPDIR=""``, and every later use becomes a path off the filesystem root —
``"$TMPDIR/site"`` is ``/site``. The empty value is dangerous because it is
quiet, which is why a static "does it look right" check is not enough.

So these tests EXECUTE the real line text lifted from the shipped scripts with
the variable empty, and pair every guarded case with the UNGUARDED CONTROL
(``test_unguarded_deletion_would_proceed_on_an_empty_path``). A guard only ever
observed passing has not been shown to guard anything; the control is what
makes the rest evidence.
"""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

import pytest

_CI_DIR = Path(__file__).resolve().parents[2] / ".github" / "ci"
_WRAPPERS = ("run-in-sif.sh", "build-in-sif.sh", "publish-in-sif.sh")


def _rm_lines(name: str) -> list[str]:
    """Every line of a wrapper that deletes the scratch path."""
    text = (_CI_DIR / name).read_text(encoding="utf-8")
    return [
        line.strip()
        for line in text.splitlines()
        if "TMPDIR" in line and line.lstrip().startswith(("rm -rf", "trap 'rm -rf"))
    ]


@lru_cache(maxsize=None)
def _run(body: str) -> tuple[int, str, str]:
    """Run ``body`` under the wrappers' own `set -euo pipefail`, TMPDIR empty."""
    script = f'set -euo pipefail\nTMPDIR=""\n{body}\necho REACHED-NEXT-LINE\n'
    proc = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False
    )
    return proc.returncode, proc.stdout, proc.stderr


# (wrapper, line) for every scratch deletion actually shipped, so each case
# below exercises the REAL text of the REAL script, not a paraphrase of it.
_DELETIONS = [(n, line) for n in _WRAPPERS for line in _rm_lines(n)]


@pytest.mark.parametrize("name", _WRAPPERS)
def test_every_wrapper_still_deletes_its_scratch(name):
    # Arrange
    wrapper = name
    # Act
    lines = _rm_lines(wrapper)
    # Assert
    assert lines, f"{wrapper} deletes no scratch path — did the lifecycle move?"


@pytest.mark.parametrize(("name", "body"), _DELETIONS)
def test_every_scratch_deletion_carries_the_guard(name, body):
    # Arrange
    expected = "${TMPDIR:?"
    # Act
    guarded = expected in body
    # Assert
    assert guarded, (
        f"{name} deletes the scratch path without the guard: `{body}`. An empty "
        "TMPDIR makes `rm -rf` a SILENT success, and the script then addresses "
        "paths off the filesystem root."
    )


def test_unguarded_deletion_would_proceed_on_an_empty_path():
    """The CONTROL. Without this case the guarded tests prove nothing."""
    # Arrange
    body = 'rm -rf "$TMPDIR"'
    # Act
    returncode, stdout, _ = _run(body)
    # Assert
    assert (returncode, "REACHED-NEXT-LINE" in stdout) == (0, True), (
        'expected `rm -rf ""` to succeed silently and let the script carry on '
        f"(rc={returncode}, out={stdout!r}). If this ever fails, the platform's "
        "rm now rejects an empty operand and the hazard has changed shape — "
        "re-measure before weakening the guard."
    )


@pytest.mark.parametrize(("name", "body"), _DELETIONS)
def test_guarded_deletion_aborts_on_an_empty_path(name, body):
    # Arrange
    command = body
    # Act
    returncode, stdout, _ = _run(command)
    # Assert
    assert returncode != 0, (
        f"{name}: `{command}` did NOT abort on an empty TMPDIR "
        f"(rc=0, out={stdout!r})"
    )


@pytest.mark.parametrize(("name", "body"), _DELETIONS)
def test_guarded_deletion_names_the_variable_it_refused(name, body):
    # Arrange
    command = body
    # Act
    _, _, stderr = _run(command)
    # Assert
    assert "TMPDIR" in stderr, (
        f"{name}: `{command}` aborted without naming TMPDIR — whoever reads the "
        f"CI log needs the variable in the message. stderr={stderr!r}"
    )


@pytest.mark.parametrize(("name", "body"), _DELETIONS)
def test_guarded_deletion_stops_execution(name, body):
    # Arrange
    command = body
    # Act
    _, stdout, _ = _run(command)
    # Assert
    assert "REACHED-NEXT-LINE" not in stdout, (
        f"{name}: `{command}` reported the refusal but execution continued"
    )
