#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The CI_RUNS_ON default must name a destination the registry DECLARES.

Two defects, measured 2026-08-15, both of which had been correct when written:

1. `_register.py` and `_use.py` each carried their OWN literal for the same
   Actions Variable, and they had drifted::

       _register.py  '["self-hosted","Linux","X64","scitex-ci"]'
       _use.py       '["self-hosted","scitex-ci"]'          <- no OS, no arch

   Nothing made them the same value, so they stopped being the same value.

2. Both named `scitex-ci`, which at ORG scope was carried by exactly four
   runners, ALL FOUR OFFLINE since 2026-08-12. GitHub does not reject a job
   whose labels nothing serves — it QUEUES IT FOREVER — so the default was
   pointing newly-registered repos at a destination that could never pick
   their work up.

WHY THE REGISTRY IS THE ORACLE, and not a hardcoded expected string. Pinning
the literal would only assert that today's value equals today's value. The
question worth asking is whether the value names something we actually run,
and `scitex_dev.hosts` is the package's own answer to that — the same source
PS-224 validates workflows against. A default that the registry cannot serve
is the exact defect these tests exist for.

WHAT THESE TESTS CANNOT DO, stated because the gap is the interesting part:
they check DECLARATION, never LIVENESS. The registry records which machines
are registered to serve a label; it says nothing about whether they are up.
On 2026-08-15 `spartan-cpu` was declared and resolvable while all four of its
carriers were offline and 57 jobs queued against it. A label census is a
measurement with an expiry date and no offline test can pin it — which is
precisely how the `scitex-ci` default rotted unnoticed.
"""

from __future__ import annotations

import json

import pytest

from scitex_dev.ci.runner._register import CI_RUNS_ON_DEFAULT
from scitex_dev.hosts import find_runner_host, packaged_default_runner_destinations


@pytest.fixture()
def the_default_labels() -> list[str]:
    """The default parsed the way a workflow parses it (`fromJSON`)."""
    return json.loads(CI_RUNS_ON_DEFAULT)


def test_the_default_is_a_json_array_of_labels(the_default_labels: list[str]) -> None:
    """A JSON STRING would also be accepted by `runs-on`, silently selecting a
    single label — so the shape is worth pinning, not just the contents."""
    # Arrange
    parsed = the_default_labels
    # Act
    is_label_list = isinstance(parsed, list) and all(
        isinstance(label, str) for label in parsed
    )
    # Assert
    assert is_label_list, f"CI_RUNS_ON default is not a JSON array: {parsed!r}"


def test_the_default_names_a_destination_the_registry_declares(
    the_default_labels: list[str],
) -> None:
    # Arrange
    wanted = the_default_labels
    # Act
    host = find_runner_host(wanted)
    # Assert
    assert host is not None, (
        f"CI_RUNS_ON default {wanted} matches NO registered runner. GitHub "
        "queues such a job forever rather than failing it, so every repo "
        "registered with this default would wait indefinitely. Declared "
        f"destinations: {sorted(packaged_default_runner_destinations())}"
    )


def test_the_default_is_self_hosted_because_that_is_this_verb_s_purpose(
    the_default_labels: list[str],
) -> None:
    """`ci runner register` exists to point a repo at hardware we own.

    NOT a revival of the repealed hosted-runner ban (operator, 2026-07-31 and
    constitution 2026-08-05: hosted is a legitimate, often preferred target).
    Hosted is reached by `ci runner use github`; this constant is the OTHER
    branch, and a hosted value here would make the two branches identical.
    """
    # Arrange
    parsed = the_default_labels
    # Act
    self_hosted = "self-hosted" in parsed
    # Assert
    assert self_hosted, (
        f"the self-hosted branch's default is {parsed}, which is not "
        "self-hosted — `use github` and `use self-hosted` would then do the "
        "same thing"
    )


def test_both_verbs_write_the_same_value() -> None:
    """`_use.py` must IMPORT the default, never re-spell it.

    Read from the module source rather than by calling the command, because
    the drift this pins is textual: two literals that were meant to be equal.
    """
    # Arrange
    from pathlib import Path

    import scitex_dev.ci.runner._use as use_mod

    source = Path(use_mod.__file__).read_text(encoding="utf-8")
    # Act
    respelled = '["self-hosted"' in source.replace(
        "CI_RUNS_ON_DEFAULT", ""
    ) and "value = CI_RUNS_ON_DEFAULT" not in source
    # Assert
    assert not respelled, (
        "`_use.py` carries its own self-hosted label literal again. One "
        "Actions Variable, one definition — the two spellings drifted last "
        "time over whether to name the OS and arch."
    )
