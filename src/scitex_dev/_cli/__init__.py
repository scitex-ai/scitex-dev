#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SciTeX-dev CLI package — entry point + reusable subcommand mixins.

Module map:
- `_root`        — top-level Click group `main` (the `scitex-dev` console script entry point)
- `_utils`       — `handle_result`, `run_as_cli`, `wrap_as_cli`, json/dry-run option helpers
- `_completion`  — shell tab-completion installer
- `_doctor`      — `scitex-dev doctor`
- `_stats`       — `scitex-dev ecosystem stats`
- `audit/`       — `_summary` (was _cli_audit), `_api`, `_project`, `_skills`
- `ecosystem/`   — `_registry` (was _cli_ecosystem)
- `quality/`     — `_check` (was _cli_quality), `_frontmatter`
- `skills/`      — `_manage` (was _cli_skills), `_tags`

The `main` callable is the `[project.scripts]` target — `scitex_dev._cli:main`
must remain importable.
"""

from __future__ import annotations

import os as _os
import sys as _sys


def _is_bare_version_invocation(argv: list[str]) -> bool:
    """True iff ``argv`` is exactly a single ``--version``/``-V`` token.

    A pure predicate (no ``sys.argv`` access) so it is unit-testable
    without spawning a subprocess. Deliberately narrow — any other
    combination (extra flags, a subcommand, ``--version --json``)
    returns False and falls through to the real Click group unchanged.

    NOTE: this predicate inspects ``argv[1:]`` ONLY. It says nothing
    about WHICH program is running, so it is NOT sufficient on its own
    to authorise printing scitex-dev's identity — see
    :func:`_should_fast_path_version`.
    """
    return argv in (["--version"], ["-V"])


#: Basenames the `scitex-dev` console script can legitimately appear as
#: in ``sys.argv[0]``. Anything else is some OTHER program that merely
#: imported us.
_ENTRY_POINT_BASENAMES = frozenset({"scitex-dev", "scitex-dev.exe"})


def _is_scitex_dev_entry_point(argv0: str) -> bool:
    """True iff ``argv0`` identifies THIS package's own console script.

    Pure predicate over ``sys.argv[0]``. Recognises the installed
    console script (``.../bin/scitex-dev``) and ``python -m scitex_dev``
    (whose ``argv[0]`` is the package's own ``__main__.py``).

    Deliberately CONSERVATIVE: anything unrecognised returns False, and
    a False merely declines the optimisation — the caller then falls
    through to the real Click group, which is the correct (just slower)
    behaviour. Declining is always safe; asserting wrongly is not.
    """
    if not argv0:
        return False
    tail = argv0.replace("\\", "/")
    if _os.path.basename(tail) in _ENTRY_POINT_BASENAMES:
        return True
    return tail.endswith("/scitex_dev/__main__.py")


def _should_fast_path_version(argv: list[str]) -> bool:
    """True iff this process is scitex-dev's OWN CLI asked for its version.

    BOTH conditions are required, and the second one is the whole point:

    * ``argv[1:]`` is a bare ``--version``/``-V`` (nothing else to do), and
    * ``argv[0]`` is scitex-dev's own console script.

    The ``argv[0]`` gate exists because this module is a SHARED
    primitive: scitex-ui, scitex-app and friends import
    ``scitex_dev._cli._completion`` / ``._root`` to build THEIR CLIs.
    Without the gate, `scitex-ui --version` imported this package,
    matched on ``argv[1:]`` alone, printed *scitex-dev's* name and
    version, and killed the process with ``SystemExit(0)`` — so every
    downstream CLI confidently reported another package's identity.
    """
    if not argv:
        return False
    return _is_bare_version_invocation(argv[1:]) and _is_scitex_dev_entry_point(argv[0])


# Fast-path a bare `--version`/`-V` invocation BEFORE importing `._root`.
# `_root`'s module-level code eagerly registers the ENTIRE subcommand
# tree (ecosystem, linter, gate, ci-runner, docs, skills, …) as a side
# effect of import — several hundred ms even though a version check
# needs none of it. `CliRunner.invoke` in tests bypasses `sys.argv`
# entirely, so this never affects test behavior — only the real
# console-script invocation (`scitex-dev --version`) sees it.
#
# This block is an OPTIMISATION, never an identity oracle: it may fire
# only when `sys.argv` proves the running program IS `scitex-dev`.
if _should_fast_path_version(_sys.argv):
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _version

    try:
        _v = _version("scitex-dev")
    except PackageNotFoundError:
        _v = "0.0.0-unknown"
    print(f"scitex-dev {_v}")
    raise SystemExit(0)

from ._root import main
from ._utils import (
    add_dry_run_argument,
    add_json_argument,
    dry_run_option,
    handle_result,
    json_option,
    run_as_cli,
    wrap_as_cli,
)

__all__ = [
    "add_dry_run_argument",
    "add_json_argument",
    "dry_run_option",
    "handle_result",
    "json_option",
    "main",
    "run_as_cli",
    "wrap_as_cli",
]
