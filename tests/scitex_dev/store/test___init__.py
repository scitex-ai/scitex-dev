#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``import scitex_dev.store`` must stay cheap.

Adopting this primitive promotes ``scitex-dev`` from a dev-only extra to a
HARD RUNTIME dependency of every leaf package that stores anything.
scitex-cards accepted that trade on one condition: importing the store must
not drag the ecosystem toolchain — linter, CI, jobs, release, ecosystem —
into a leaf's runtime. Otherwise one coupling has been traded for a much
larger one.

This is that condition, checked rather than promised. Each case runs in a
SUBPROCESS, because once a heavy module is imported anywhere in the test
session it is in ``sys.modules`` forever and an in-process assertion would
pass for the wrong reason.

If this file starts failing, the fix is to make the import lighter — not to
shorten the forbidden list. A gate loosened until it passes is the same as
a deleted gate, except that everyone still believes it works.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

#: Modules whose presence would mean the ecosystem toolchain came along.
FORBIDDEN = (
    "scitex_dev.linter",
    "scitex_dev.ci",
    "scitex_dev.jobs",
    "scitex_dev._release",
    "scitex_dev._ecosystem",
    "scitex_dev.dashboard",
    "scitex_dev.gate",
)

_PROBE = """
import sys
import scitex_dev.store  # noqa: F401
loaded = [name for name in sys.modules if name.startswith("scitex_dev.")]
print("\\n".join(sorted(loaded)))
"""


def _imported_modules() -> set[str]:
    """Import the store in a clean interpreter; report what came with it."""
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise AssertionError(
            "importing scitex_dev.store failed in a subprocess:\n"
            f"{completed.stderr}"
        )
    return set(completed.stdout.split())


@pytest.fixture(scope="module")
def loaded_modules() -> set[str]:
    """What a bare ``import scitex_dev.store`` actually pulls in."""
    return _imported_modules()


@pytest.mark.parametrize("heavy", FORBIDDEN)
def test_importing_the_store_does_not_load_the_heavy_module(loaded_modules, heavy):
    """No ecosystem-toolchain module may ride along with the store."""
    # Arrange
    present = {name for name in loaded_modules if name.startswith(heavy)}

    # Act
    offenders = sorted(present)

    # Assert
    assert offenders == []


def test_importing_the_store_does_not_load_psycopg():
    """The Postgres driver is extra-gated and must stay unimported."""
    # Arrange
    probe = "import sys, scitex_dev.store; print('psycopg' in sys.modules)"

    # Act
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )

    # Assert
    assert completed.stdout.strip() == "False"


def test_importing_the_store_does_not_require_scitex_config():
    """``scitex_config`` is touched lazily, only to resolve a path.

    A leaf that constructs its own :class:`StoreTarget` with an explicit
    locator must not need the config package installed at all.
    """
    # Arrange
    probe = "import sys, scitex_dev.store; print('scitex_config' in sys.modules)"

    # Act
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, timeout=120
    )

    # Assert
    assert completed.stdout.strip() == "False"


def test_the_store_imports_at_all_in_a_clean_interpreter(loaded_modules):
    """A positive control: the gate above must not pass by nothing loading."""
    # Arrange
    expected = "scitex_dev.store"

    # Act
    present = expected in loaded_modules

    # Assert
    assert present is True

# EOF
