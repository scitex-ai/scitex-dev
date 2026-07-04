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

import sys as _sys


def _is_bare_version_invocation(argv: list[str]) -> bool:
    """True iff ``argv`` is exactly a single ``--version``/``-V`` token.

    A pure predicate (no ``sys.argv`` access) so it is unit-testable
    without spawning a subprocess. Deliberately narrow — any other
    combination (extra flags, a subcommand, ``--version --json``)
    returns False and falls through to the real Click group unchanged.
    """
    return argv in (["--version"], ["-V"])


# Fast-path a bare `--version`/`-V` invocation BEFORE importing `._root`.
# `_root`'s module-level code eagerly registers the ENTIRE subcommand
# tree (ecosystem, linter, gate, ci-runner, docs, skills, …) as a side
# effect of import — several hundred ms even though a version check
# needs none of it. `CliRunner.invoke` in tests bypasses `sys.argv`
# entirely, so this never affects test behavior — only the real
# console-script invocation (`scitex-dev --version`) sees it.
if _is_bare_version_invocation(_sys.argv[1:]):
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
