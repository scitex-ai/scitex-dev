"""`import scitex_dev` must not pull `importlib.metadata` onto the path.

Reading package metadata drags in `email.message`, `email.utils` and
`zipfile` — an email parser, to learn a version string. Measured by
scitex-cards on their own package, 2026-07-30: 223ms of a 425ms cold
import, 52%, for one module-scope statement sitting above a fully correct
PEP 562 lazy loader.

WHY THESE ASSERT STRUCTURE AND NOT TIMING
A timing assertion is load-dependent and flakes; scitex-cards measured
their own pre-fix import ranging 325→763ms across five samples on one
machine. The binary "is it on the path" question is load-independent and
fails the moment someone re-adds an eager read. Without it the
optimisation silently rots back — which is the only reason a perf fix
gets a test at all.

The probes run in SUBPROCESSES with an absolute interpreter path. A bare
`python` would leave "which interpreter answered" unrecorded, which is the
same defect as an ambiguous dist-info wearing different clothes.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[2] / "src")


def _probe(body: str) -> str:
    """Run `body` in a fresh interpreter with this worktree on the path."""
    out = subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": _SRC, "PATH": "/usr/bin:/bin"},
        timeout=120,
    )
    return out.stdout.strip()


def test_bare_interpreter_does_not_already_have_it():
    """POSITIVE CONTROL — without this the real test proves nothing.

    If the interpreter already imported `importlib.metadata` at startup,
    every assertion below would be pre-satisfied or pre-failed for reasons
    unrelated to this package.
    """
    # Arrange
    body = "import sys; print('importlib.metadata' in sys.modules)"
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "False"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "KNOWN REMAINING PATH, not a flake. Deferring `__version__` removed "
        "ONE of two eager metadata reads. The other is a CALL at module "
        "scope: `__init__.py:205` runs `_emit_drift('scitex-dev')`, and the "
        "metadata read lives inside `emit_if_drift` — `check_editable_drift` "
        "imports only json/os/shutil/subprocess/sys/time/Path itself, so no "
        "grep for a module-scope `importlib.metadata` import finds it. "
        "Deferring that call is a BEHAVIOUR change (the drift warning fires "
        "once per process by design) and wants its own reasoning, so it is "
        "not smuggled in here. strict=True on purpose: this flips to a "
        "FAILURE the day someone fixes the drift call, which is the "
        "notification we want. A passing assertion would be a lie and a "
        "deleted one would let the `__version__` fix rot back."
    ),
)
def test_importing_scitex_dev_does_not_load_importlib_metadata():
    """The END-STATE assertion — currently unmet, deliberately kept."""
    # Arrange
    body = "import sys, scitex_dev; print('importlib.metadata' in sys.modules)"
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "False"


def test_init_itself_no_longer_reads_metadata_at_module_scope():
    """What this change DID achieve, asserted without overclaiming.

    The `__init__.py` module body must contain no top-level
    `importlib.metadata` import. Indented occurrences (inside
    `_resolve_version`) are exactly the deferral we want, so the check is
    on INDENTATION, not on the substring appearing anywhere.
    """
    # Arrange
    src = Path(_SRC) / "scitex_dev" / "__init__.py"
    # Act
    top_level = [
        ln
        for ln in src.read_text().splitlines()
        if ln.startswith(("from importlib.metadata", "import importlib.metadata"))
    ]
    # Assert
    assert top_level == []


def test_attribute_access_still_returns_a_version():
    """Deferred, not deleted."""
    # Arrange
    body = "import scitex_dev; print(bool(scitex_dev.__version__))"
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "True"


def test_from_import_form_still_returns_a_version():
    """`from X import __version__` is a DIFFERENT code path than `X.__version__`.

    Both route through PEP 562, but a test of one does not cover the other,
    and this repo has a live caller of the `from` form at
    `_cli/audit/_cache.py:98`.
    """
    # Arrange
    body = "from scitex_dev import __version__; print(bool(__version__))"
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "True"


def test_touching_version_does_load_it_deferred_not_deleted():
    """The read still happens — just on demand rather than on import."""
    # Arrange
    body = (
        "import sys, scitex_dev; _ = scitex_dev.__version__; "
        "print('importlib.metadata' in sys.modules)"
    )
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "True"


def test_version_is_cached_after_first_access():
    """PEP 562 must not be consulted twice for the same attribute."""
    # Arrange
    body = (
        "import scitex_dev; _ = scitex_dev.__version__; "
        "print('__version__' in vars(scitex_dev))"
    )
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "True"


def test_version_stays_in_all_for_dir_and_completion():
    """Dropping it from __all__ is a silent public-surface regression."""
    # Arrange
    body = "import scitex_dev; print('__version__' in scitex_dev.__all__)"
    # Act
    verdict = _probe(body)
    # Assert
    assert verdict == "True"


# EOF
