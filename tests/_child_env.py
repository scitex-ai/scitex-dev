#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""What a hand-built child environment still owes the dynamic loader.

Several suites run a REAL subprocess with an explicitly constructed
``env=`` instead of an inherited one, because the thing they measure —
import ordering, a stripped ``$PATH``, which tier a hook's probe picks —
is destroyed by whatever the developer happens to export. That reasoning
is right and none of it changes here.

``LD_LIBRARY_PATH`` is not one of those things, and every one of them
swept it up anyway. It is not a knob the code under test reads. It is
what the DYNAMIC LOADER needs to start the interpreter at all, before
the first line of any script runs. A test cannot choose to leave it out
any more than it can choose to leave out the binary.

Dropping it cost nothing on the Spartan runners, whose interpreter found
its libpython on the default loader path, so it went unnoticed for as
long as those runners existed. setup-python's 3.11 and 3.13 builds on
the scitex-compute nodes live in the tool cache and link against
``libpython3.X.so.1.0`` beside them, reachable only through
``LD_LIBRARY_PATH`` — which the job exports, correctly, and these calls
then threw away.

Measured 2026-08-12 on `pytest-matrix` py3.11: 21 failures and 4 errors
across four files, every one of them a child that died with

    error while loading shared libraries: libpython3.11.so.1.0

BEFORE running, and a test that then reported a verdict on an experiment
that never happened — `SUBPROCESS_FAILED rc=127`, or an empty stdout
compared against `'True'`. py3.12's build resolves its libpython without
the variable, which is why this hid on two interpreters and not the
third, and why it looked like an unrelated matrix flake.
"""

from __future__ import annotations

import os

#: Variables a constructed child env must carry for the interpreter to
#: START. These are not configuration — they are preconditions for
#: execution, and a test that omits them measures nothing.
_LOADER_VARS = ("LD_LIBRARY_PATH",)


def with_loader_path(env: dict) -> dict:
    """Return ``env`` plus whatever the dynamic loader needs, when set.

    Only variables the PARENT actually has are copied, so the child env
    stays exactly as minimal as the caller intended on hosts where
    nothing needs them — which is every host this suite ran on before
    the CI move, and the reason the omission was invisible.
    """
    out = dict(env)
    for name in _LOADER_VARS:
        value = os.environ.get(name)
        if value:
            out[name] = value
    return out


# EOF
