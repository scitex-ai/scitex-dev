#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""``scitex_dev.store``'s facade: what it costs to import, and what it exports.

Two properties of the same file, kept together because they are the same
promise to a leaf package — that ``from scitex_dev.store import ...`` is
cheap, and that the names it advertises are actually there.

PART ONE: ``import scitex_dev.store`` must stay cheap.

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

PART TWO: the public surface leaves PIN.

sac and scitex-cards both write ``from scitex_dev.store import ...`` and
register an entry point against ``scitex_dev.store.plugins``. Those two
strings are a CONTRACT with packages this repo does not control, and moving
either one breaks them in the quietest possible way: discovery finds
nothing and reports an empty federation, which is indistinguishable from
"no leaf has adopted the store yet".

The error-class cases are a regression on a real defect.
``SupersededFenceError`` was raised by the replay path and listed in
``_errors.__all__`` but never re-exported here, so no caller could name it
in an ``except`` clause. A fence nobody can catch is a crash, not a guard.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import scitex_dev.store as store

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


# -- part two: the exported surface ------------------------------------


def test_every_exported_name_resolves():
    # Arrange — an `__all__` entry with no attribute behind it is a
    # `from ... import *` that raises, and a documentation claim that lies.
    # Act
    missing = [name for name in store.__all__ if not hasattr(store, name)]
    # Assert
    assert missing == []


def test_the_exported_names_are_sorted():
    # Arrange — kept sorted so two people adding a name in the same week
    # conflict in one place rather than shuffling the list.
    # Act
    got = list(store.__all__)
    # Assert
    assert got == sorted(got)


def test_superseded_fence_error_is_exported():
    # Arrange — DEFECT FIX. It was reachable only as
    # `scitex_dev.store._errors.SupersededFenceError`, a private path no
    # caller should import from.
    # Act
    exported = "SupersededFenceError" in store.__all__
    # Assert
    assert exported is True


def test_a_superseded_fence_can_be_caught_by_name():
    # Arrange — the property that matters, not merely the attribute's
    # presence: a guard whose exception cannot be named is a crash.
    caught = None
    # Act
    try:
        raise store.SupersededFenceError("demoted writer still emitting")
    except store.SupersededFenceError as exc:
        caught = exc
    # Assert
    assert str(caught) == "demoted writer still emitting"


def test_a_superseded_fence_is_a_store_error():
    # Arrange — a caller handling the whole primitive with one clause must
    # not be surprised by this one escaping.
    # Act
    got = issubclass(store.SupersededFenceError, store.StoreError)
    # Assert
    assert got is True


def test_the_fence_assertion_is_exported():
    # Arrange — it is a plain function precisely so it can be called and
    # tested on its own; that is worth nothing if it is not reachable.
    # Act
    exported = "assert_not_superseded" in store.__all__
    # Assert
    assert exported is True


def test_the_federation_entry_point_is_reachable_from_the_facade():
    # Arrange — this is the exact import sac PR #1020 and scitex-cards make.
    # Act
    got = callable(store.discover_store_plugins)
    # Assert
    assert got is True


def test_the_plugin_contract_is_reachable_from_the_facade():
    # Arrange
    # Act
    got = store.StorePlugin.__name__
    # Assert
    assert got == "StorePlugin"


def test_the_entry_point_group_is_reachable_from_the_facade():
    # Arrange — leaves read this constant rather than retyping the string.
    # Act
    got = store.ENTRY_POINT_GROUP
    # Assert
    assert got == "scitex_dev.store.plugins"


def test_divergence_detection_is_reachable_from_the_facade():
    # Arrange
    # Act
    got = callable(store.detect_divergence)
    # Assert
    assert got is True


def test_identity_comparison_is_reachable_from_the_facade():
    # Arrange
    # Act
    got = callable(store.assert_same_store)
    # Assert
    assert got is True

# EOF
